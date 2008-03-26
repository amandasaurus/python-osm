#! /usr/bin/python
import xml.sax

class Node(object):
    def __init__(self, id=None, lon=None, lat=None, tags=None):
        self.id = id
        self.lon, self.lat = lon, lat
        if tags:
            self.tags = tags
        else:
            self.tags = {}

    def __repr__(self):
        return "Node(id=%r, lon=%r, lat=%r, tags=%r)" % (self.id, self.lon, self.lat, self.tags)

class Way(object):
    def __init__(self, id, nodes=None, tags=None):
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

class NodePlaceHolder(object):
    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "NodePlaceHolder(id=%r)" % (self.id)

class OSMXMLFile(object):
    def __init__(self, filename):
        self.filename = filename

        self.nodes = {}
        self.ways = {}
        self.__parse()
        print repr(self.ways)

    def __parse(self):
        """Parse the given XML file"""
        parser = xml.sax.make_parser()
        parser.setContentHandler(OSMXMLFileParser(self))
        parser.parse(self.filename)

        # now fix up all the refereneces
        for way in self.ways.values():
            way.nodes = [self.nodes[node_pl.id] for node_pl in way.nodes]

        # convert them back to lists
        self.nodes = self.nodes.values()
        self.ways = self.ways.values()


class OSMXMLFileParser(xml.sax.ContentHandler):
    def __init__(self, containing_obj):
        self.containing_obj = containing_obj
        self.curr_node = None
        self.curr_way = None

    def startElement(self, name, attrs):
        #print "Start of node " + name
        if name == 'node':
            self.curr_node = Node(id=attrs['id'], lon=attrs['lon'], lat=attrs['lat'])
        elif name == 'way':
            #self.containing_obj.ways.append(Way())
            self.curr_way = Way(id=attrs['id'])
        elif name == 'tag':
            #assert not self.curr_node and not self.curr_way, "curr_node (%r) and curr_way (%r) are both non-None" % (self.curr_node, self.curr_way)
            if self.curr_node:
                self.curr_node.tags[attrs['k']] = attrs['v']
            elif self.curr_way:
                self.curr_way.tags[attrs['k']] = attrs['v']
        elif name == "nd":
            assert self.curr_node is None, "curr_node (%r) is non-none" % (self.curr_node)
            assert self.curr_way is not None, "curr_way is None"
            self.curr_way.nodes.append(NodePlaceHolder(id=attrs['ref']))


    def endElement(self, name):
        #print "End of node " + name
        #assert not self.curr_node and not self.curr_way, "curr_node (%r) and curr_way (%r) are both non-None" % (self.curr_node, self.curr_way)
        if name == "node":
            self.containing_obj.nodes[self.curr_node.id] = self.curr_node
            self.curr_node = None
        elif name == "way":
            self.containing_obj.ways[self.curr_way.id] = self.curr_way
            self.curr_way = None

if __name__ == '__main__':
    osm = OSMXMLFile("./lucan.osm.xml")



