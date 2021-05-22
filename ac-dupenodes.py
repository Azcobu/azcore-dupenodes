'''
Azeroth Core Proximate Node Finder
Identifies resource nodes in AC DB that are too close to each other.

Queries - not all nodes are members of a pool?
As pools can spawn multiple members, does pool membership even need to
be checked?
To do: given a set of XYZ coords, find if any nodes in the DB are already
too close to given coords. This would help with later node replacement/repopulation.
.002 - added x-pos culling, avoiding search of all remaining nodes in favour
	   of just local ones, making node search ~10 times faster.
'''
# map id: 0 = Eastern Kingdoms, 1 = Kalimdor, 530 = Outland, 571 = Northrend
# DB tables - gameobject lists all spawns
#           - pool_gameobject - links guids and pool ids

from os import listdir
from mysql.connector import connect, Error
import time

class Node: # an individual resource spawn
    def __init__(self, name, guid, objid, mapid, x, y, z, pool=None, desc=None):
        self.name = name
        self.guid = guid
        self.objid = objid
        self.mapid = mapid
        self.x = x
        self.y = y
        self.z = z
        self.pool = pool
        self.desc = desc

    def __repr__(self):
        outstr = f'{self.name}, ID: {self.guid} at X: {self.x}, Y: {self.y}, Z: {self.z}'
        if self.pool:
            outstr += f', Pool: {self.pool}, Desc: {self.desc}'
        return outstr

    def calc_distance(self, node2):
        if self.mapid == node2.mapid:
            if self.pool == None or self.pool != node2.pool:
                dist = ((self.x - node2.x) ** 2 + (self.y - node2.y) ** 2 +\
                       (self.z - node2.z) ** 2) ** 0.5
                return round(dist, 2)
        return 10**9 # arbitrary large number

class Resource: # a generic resource type, like iron or copper
    def __init__(self, name, skill, entry_id=[]):
        self.name = name
        self.skill = skill # required skill to access node, useful for zone culling
        self.entry_id = entry_id

    def __repr__(self):
        return f'Resource: {self.name}, entries: {self.entry_id}'

def brute_nodesearch(nodelist, max_dist=3, skillcull=150):
    # brute force search for closest nodes, good enough for low node counts
    # skillcull tracks difference in skill needed to access a node, so
    # helps prevent comparing e.g. copper to saronite.
    results = []

    for pos, n1 in enumerate(nodelist):
        for n2 in nodelist[pos+1:]:
            if abs(n1.x - n2.x) > max_dist: # cull based on x distance
                break
            else:
                currdist = n1.calc_distance(n2)
                if currdist < max_dist:
                    results.append([n1, n2, currdist])

    results = sorted(results, key=lambda x:x[2])
    print(f'{len(results)} node pairs within {max_dist} units found.')
    return results

def export_results(outfile, data):
    with open(outfile, 'w') as out:
        for num, x in enumerate(data):
            out.write(f'{num+1}. {x[0]} -> {x[1]}, distance {x[2]} units.\n\n')
    print(f'Data written to {outfile}')

def open_sql_db(db_user, db_pass):
    try:
        db = connect(host = 'localhost',
                     database = 'acore_world',
                     user = db_user,
                     password = db_pass)
        if db.is_connected():
            print('Connected to AzCore database, reading node data...')
    except Error as e:
        print(e)

    return db, db.cursor()

def import_sql_node_data(db_user, db_pass, resource_type):
    # just does ores for now, they seem to be more of a problem than herbs
    # note that skill lvls for nodes with very similar names, i.e.
    # cobalt/rich cobalt may be slightly off, but not enough to throw
    # off skill culling
    resources, nodelist = [], []

    ores = ['Copper Vein', 'Tin Vein', 'Silver Vein', 'Iron Deposit',
            'Gold Vein', 'Mithril Deposit', 'Truesilver Deposit',
            'Small Thorium Vein', 'Dark Iron Deposit', 'Rich Thorium Vein',
            'Adamantite Deposit', 'Cobalt Deposit', 'Khorium Vein',
            'Saronite Deposit', 'Titanium Vein']

    # TODO: need to check the escaped apostrophes aren't messing things up
    herbs = {'Peacebloom', 'Silverleaf', 'Earthroot', 'Mageroyal',
             'Briarthorn', 'Stranglekelp', 'Bruiseweed','Wild Steelbloom',
             'Grave Moss', 'Kingsblood', 'Liferoot', 'Fadeleaf', 'Goldthorn',
             "Khadgar\\'s Whisker", 'Wintersbite', 'Firebloom',
             'Purple Lotus', "Arthas\\' Tears", 'Sungrass', 'Blindweed',
             'Ghost Mushroom', 'Gromsblood', 'Golden Sansam', 'Dreamfoil',
             'Mountain Silversage', 'Plaguebloom', 'Icecap', 'Black Lotus',
             'Felweed', 'Dreaming Glory', 'Ragveil', 'Terocone',
             'Flame Cap', 'Goldclover', 'Nightmare Vine', 'Mana Thistle',
             'Tiger Lily', "Talandra\\'s Rose",  "Adder\\'s Tongue",
             'Frozen Herb', 'Lichbloom', 'Icethorn', 'Frost Lotus'}

    #ores = ['Small Thorium Vein', 'Gold Vein'] #testbed

    curr_resource = ores if resource_type == 'ores' else herbs
    curr_resource = '(' + ', '.join([f"'{x}'" for x in curr_resource]) + ')'

    db, cursor = open_sql_db(db_user, db_pass)

    query = ("SELECT got.name, go.guid, id, map, position_x, position_y, position_z, pool_entry, description "
             "FROM `gameobject` go "
             "JOIN `gameobject_template` got ON got.entry = go.id "
             "LEFT JOIN `pool_gameobject` pgo ON go.guid = pgo.guid "
             f"WHERE name IN {curr_resource}")
    cursor.execute(query)
    results = cursor.fetchall()
    for x in results:
        newnode = Node(*x)
        nodelist.append(newnode)

    print(f'{len(nodelist)} node entries read.')
    cursor.close()
    db.close()
    nodelist = sorted(nodelist, key=lambda node:node.x) #sort by x-pos for culling
    return nodelist

def main():
	start = time.time()
	db_user = 'root' # for local AzCore world DB, change as needed
	db_pass = 'password'
	nodelist = import_sql_node_data(db_user, db_pass, 'herbs')
	found = brute_nodesearch(nodelist, 3)
	export_results('azcore-duplicate-nodes.txt', found)
	runtime = time.time() - start
	print(f'Total runtime is {round(runtime, 2)} seconds.')

if __name__ == '__main__':
    main()
