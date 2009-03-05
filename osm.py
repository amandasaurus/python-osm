#! /usr/bin/python
import xml.sax, math, tempfile, urllib, urllib2, os
import StringIO

OSM_API_BASE_URL = "http://api.openstreetmaps.org/api/0.5"

class Property(object):
    """
    A metaclass to make it easy to add properties to objects
    """
    class __metaclass__(type):
        def __init__(cls, name, bases, dct):
            for fname in ['get', 'set', 'delete']:
                if fname in dct:
                    setattr(cls, fname, staticmethod(dct[fname]))
        def __get__(cls, obj, objtype=None):
            if obj is None:
                return cls
            fget = getattr(cls, 'get')
            return fget(obj)
        def __set__(cls, obj, value):
            fset = getattr(cls, 'set')
            fset(obj, value)
        def __delete__(cls, obj):
            fdel = getattr(cls, 'delete')
            fdel(obj)


class BBox(object):
    __slots__ = ['left', 'right', 'top', 'bottom']
    def __init__(self, *args, **kwargs):
        if sorted(kwargs.keys()) == ['bottom', 'left', 'right', 'top']:
            self.left = kwargs['left']
            self.right = kwargs['right']
            self.top = kwargs['top']
            self.bottom = kwargs['bottom']
        elif sorted(kwargs.keys()) == ['maxlat', 'maxlon', 'minlat', 'minlon']:
            self.left = kwargs['minlat']
            self.right = kwargs['maxlat']
            self.bottom = kwargs['maxlon']
            self.top = kwargs['minlon']
        else:
            raise TypeError("Insufficent arguments to BBox contsructor")

    class minlat(Property):
        def get(self):
            return self.left
        def set(self, value):
            self.left = value

    class maxlat(Property):
        def get(self):
            return self.right
        def set(self, value):
            self.right = value

    class minlon(Property):
        def get(self):
            return self.top
        def set(self, value):
            self.top = value

    class maxlon(Property):
        def get(self):
            return self.bottom
        def set(self, value):
            self.bottom = value

    def __repr__(self):
        return "BBox(left=%r, bottom=%r, right=%r, top=%r)" % (self.left, self.bottom, self.right, self.top)

    def __in__(self, obj):
        if instanceof(obj, Node):
            return self.minlat < node.lat < self.maxlat and self.minlon < node.lon < self.maxlon
        else:
            raise TypeError("Object %r is not a node" % obj)

class Node(object):
    __slots__ = ['id', 'lon', 'lat', 'tags']

    def __init__(self, id=None, lon=None, lat=None, tags=None):
        self.id = id
        self.lon, self.lat = lon, lat
        if tags:
            self.tags = tags
        else:
            self.tags = {}

    def __repr__(self):
        return "Node(id=%r, lon=%r, lat=%r, tags=%r)" % (self.id, self.lon, self.lat, self.tags)

    def distance(self, other):
        """
        Returns the distance between this point the other in metres
        """
        lat1=float(self.lat) * math.pi / 180
        lat2=float(other.lat) * math.pi / 180
        lon1=float(self.lon) * math.pi / 180
        lon2=float(other.lon) * math.pi / 180
        dist = math.atan(math.sqrt(math.pow(math.cos(lat2)*math.sin(abs(lon1-lon2)),2) + math.pow(math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(lon1-lon2),2)) / (math.sin(lat1)*math.sin(lat2) + math.cos(lat1)*math.cos(lat2)*math.cos(lon1-lon2)))
        dist *= 6372795 # convert from radians to meters
        return dist

class Way(object):
    __slots__ = ['id', 'nodes', 'tags']

    def __init__(self, id=None, nodes=None, tags=None):
        self.id = id
        if nodes:
            self.nodes = nodes
        else:
            self.nodes = []
        if tags:
            self.tags = tags
        else:
            self.tags = {}

    def __repr__(self):
        return "Way(id=%r, nodes=%r, tags=%r)" % (self.id, self.nodes, self.tags)

    def __len__(self):
        """
        Returns the length of the way in metres
        """
        if len(self.nodes) < 2:
            return 0
        return sum(self.nodes[i].distance(self.nodes[i+1]) for i in range(len(self.nodes)-1))



class NodePlaceHolder(object):
    __slots__ = ['id']

    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "NodePlaceHolder(id=%r)" % (self.id)

class WayPlaceHolder(object):
    __slots__ = ['id']

    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "WayPlaceHolder(id=%r)" % (self.id)

class RelationPlaceHolder(object):
    __slots__ = ['id']

    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "RelationPlaceHolder(id=%r)" % (self.id)

class Relation(object):
    __slots__ = ['id', 'roles', 'tags']

    def __init__(self, id):
        self.id = id
        self.roles = {}
        self.tags = {}

    def add(self, item, role=None):
        """
        Add the item to this relation with that role. If role is unspecified,
        it's ""
        """
        if role == None:
            role = ""

        if role not in self.roles:
            self.roles[role] = set()
        self.roles[role].add(item)



class OSMXMLFile(object):
    def __init__(self, datasource, parser=None):
        self.datasource = datasource


        self.nodes = {}
        self.ways = {}
        self.relations = {}
        self.invalid_ways = []
        self.__parse()


    def __parse(self):
        """Parse the given XML file"""

        if self.parser:
            parser = self.parser(self)
        else:
            parser = OSMXMLFileParser(self)

        if isinstance(self.datasource, basestring):
            parser = xml.sax.parseString(self.datasource, parser)
        else:
            parser = xml.sax.parse(self.datasource, parser)

        # now fix up all the refereneces
        for index, way in self.ways.items():
            try:
                way.nodes = [self.nodes[node_pl.id] for node_pl in way.nodes]
            except KeyError:
                print "Way (id=%s) referes to a node that doesn't exist, skipping that way" % (index)
                self.invalid_ways.append(way)
                del self.ways[index]
                continue

        # convert them back to lists
        self.nodes = self.nodes.values()
        self.ways = self.ways.values()


class OSMXMLFileParser(xml.sax.ContentHandler):
    def __init__(self, containing_obj):
        self.containing_obj = containing_obj
        self.curr_node = None
        self.curr_way = None
        self.curr_relation = None

    def startElement(self, name, attrs):
        #print "Start of node " + name
        if name == 'node':
            self.curr_node = Node(id=attrs['id'], lon=attrs['lon'], lat=attrs['lat'])
        elif name == 'way':
            #self.containing_obj.ways.append(Way())
            self.curr_way = Way(id=attrs['id'])
        elif name == 'relation':
            self.curr_relation = Relation(id=attrs['id'])
        elif name == 'tag':
            #assert not self.curr_node and not self.curr_way, "curr_node (%r) and curr_way (%r) are both non-None" % (self.curr_node, self.curr_way)
            if self.curr_node is not None:
                self.curr_node.tags[attrs['k']] = attrs['v']
            elif self.curr_way is not None:
                self.curr_way.tags[attrs['k']] = attrs['v']
        elif name == "nd":
            assert self.curr_node is None, "curr_node (%r) is non-none" % (self.curr_node)
            assert self.curr_way is not None, "curr_way is None"
            self.curr_way.nodes.append(NodePlaceHolder(id=attrs['ref']))
        elif name == "member":
            #import pdb ; pdb.set_trace()
            assert self.curr_relation is not None, "<member> tag and no relation"
            if attrs['type'] == 'way':
                self.curr_relation.add(WayPlaceHolder(id=attrs['ref']), role=attrs['role'])
            elif attrs['type'] == 'node':
                self.curr_relation.add(NodePlaceHolder(id=attrs['ref']), role=attrs['role'])
            elif attrs['type'] == 'relation':
                self.curr_relation.add(RelationPlaceHolder(id=attrs['ref']), role=attrs['role'])
            else:
                assert False, "Unknown member type "+repr(attrs['type'])
        elif name in ["osm", "bounds"]:
            pass
        else:
            print "Unknown node: "+name


    def endElement(self, name):
        #print "End of node " + name
        #assert not self.curr_node and not self.curr_way, "curr_node (%r) and curr_way (%r) are both non-None" % (self.curr_node, self.curr_way)
        if name == "node":

            node = self.filter(self.curr_node)
            if node is not None:
                self.containing_obj.nodes[node.id] = node

            self.curr_node = None

        elif name == "way":

            way = self.filter(self.curr_way)
            if way is not None:
                self.containing_obj.ways[way.id] = way

            self.curr_way = None

    def filter(self, item):
        return item

class GPSData(object):
    """
    Downloads data GPS track data from OpenStreetMap Server
    """
    def __init__(self, bbox, download=True):
        self.bbox = bbox
        self.tracks = []
        if download:
            self._download_from_api()

    def _download_from_api(self):
        url = "http://api.openstreetmap.org/api/0.5/trackpoints?bbox=%s,%s,%s,%s&page=%%d" % (
            self.bbox.left, self.bbox.bottom, self.bbox.right, self.bbox.top)

        page = 0
        point_last_time = None

        while page == 0 or point_last_time == 5000:
            tmpfile_fp, tmpfilename = tempfile.mkstemp(suffix=".gpx",
                prefix="osm-gps_%s,%s,%s,%s_%d_" % (self.bbox.left, self.bbox.bottom, self.bbox.right, self.bbox.top, page))
            urllib.urlretrieve(url % page, filename=tmpfilename )
            old_points_total = sum(len(way.nodes) for way in self.tracks)
            self._parse_file(tmpfilename)
            os.remove(tmpfilename)
            point_last_time = sum(len(way.nodes) for way in self.tracks) - old_points_total
            page += 1


    def _parse_file(self, filename):
        parser = xml.sax.make_parser()
        parser.setContentHandler(GPXParser(self))
        parser.parse(filename)

    def save(self, filename):
        fp = open(filename, 'w')
        fp.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        fp.write("<gpx version=\"1.0\" creator=\"PyOSM\" xmlns=\"http://www.topografix.com/GPS/1/0/\">\n")
        for track in self.tracks:
            fp.write(" <trk>\n  <trkseg>\n")
            for node in track.nodes:
                fp.write('   <trkpt lat="%s" lon="%s" />\n' % (node.lat, node.lon))
            fp.write("  </trkseg>\n </trk>\n")
        fp.write("</gpx>")
        fp.close()

class GPXParser(xml.sax.ContentHandler):
    """
    Parses GPX files from the OSM GPS trackpoint downloader. Converts them to OSM format
    """
    def __init__(self, containing_obj):
        self.tracks = []
        self.__current_way = None
        self.containing_obj = containing_obj

    def startElement(self, name, attrs):
        if name == "trkseg":
            self.__current_way = Way()
        elif name == "trkpt":
            assert self.__current_way is not None, "Invalid GPX file, we've encountered a trkpt tag before a trkseg tag"
            self.__current_way.nodes.append(Node(lat=attrs['lat'], lon=attrs['lon']))

    def endElement(self, name):
        if name == 'trkseg':
            self.containing_obj.tracks.append(self.__current_way)
            self.__current_way = None

class OSMServer(object):
    def __init__(self, api_root):
        self.api_root = api_root

    def _get_data(self, subpath):
        if subpath[0] != '/' and self.api_root[-1] != '/':
            # print a warning?
            pass
        return urllib2.urlopen(self.api_root + subpath).read()


    def node(self, node_id):
        osm_data = OSMXMLFile(self._get_data("node/%s" % node_id))

        if len(osm_data.nodes) == 0:
            # no nodes found
            return None
        elif len(osm_data.nodes) == 1:
            return osm_data.nodes[0]

    def way(self, way_id):
        osm_data = OSMXMLFile(self._get_data("way/%s" % way_id))

        if len(osm_data.ways) == 0:
            # no ways found
            return None
        elif len(osm_data.ways) == 1:
            return osm_data.ways[0]

    def relation(self, relation_id):
        osm_data = OSMXMLFile(self._get_data("relation/%s" % relation_id))

        if len(osm_data.relations) == 0:
            # no relations found
            return None
        elif len(osm_data.relations) == 1:
            return osm_data.relations[0]


# Mark Pilgram's excellent openAnything
def open_anything(source):
    # try to open with urllib (if source is http, ftp, or file URL)
    try:
        return urllib.urlopen(source)
    except (IOError, OSError):
        pass

    # try to open with native open function (if source is pathname)
    try:
        return open(source)
    except (IOError, OSError):
        pass

    # treat source as string
    return StringIO.StringIO(str(source))



osm_web = OSMServer("http://api.openstreetmap.org/api/0.5/")
