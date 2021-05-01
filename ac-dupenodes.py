'''
Azeroth Core Proximate Node Finder
Identifies resource nodes in AC DB that are too close to each other.
 
Queries - not all nodes are members of a pool?
As pools can spawn multiple members, does pool membership even need to
be checked? Not doing so atm, but may need to?

'''
# map id: 0 = Eastern Kingdoms, 1 = Kalimdor, 530 = Outland, 571 = Northrend
# DB tables - gameobject lists all spawns
#           - pool_gameobject - links guids and pool ids

from os import listdir
from mysql.connector import connect, Error
from tqdm import tqdm

class Node: # an individual resource spawn
    def __init__(self, guid, objid, mapid, x, y, z, name, skill, pool=None, desc=None):
        self.guid = guid
        self.objid = objid
        self.mapid = mapid
        self.x = x
        self.y = y
        self.z = z
        self.name = name
        self.skill = skill
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

    for pos, n1 in enumerate(tqdm(nodelist)):
        for n2 in nodelist[pos+1:]:
            if abs(n1.skill - n2.skill) <= skillcull:
                currdist = n1.calc_distance(n2)
                if currdist < max_dist:
                    results.append([n1, n2, currdist])

    results = sorted(results, key=lambda x:x[2]) # sort by distance apart
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
            print('Connected to AzCore database.')
    except Error as e:
        print(e) 
    return db, db.cursor()
    
def import_sql_node_data(db_user, db_pass, resource_type):
    # just does ores for now, they seem to be more of a problem than herbs
    # note that skill lvls for nodes with very similar names, i.e.
    # cobalt/rich cobalt may be slightly off, but not enough to throw
    # off skill culling
    resources, nodelist = [], []
        
    ores = {'Copper Vein':1, 'Tin Vein':65, 'Silver Vein':75, 
            'Iron Deposit':125, 'Gold Vein':155, 'Mithril Deposit':175,
            'Truesilver Deposit':205, 'Small Thorium Vein':230, 
            'Dark Iron Deposit':230, 'Rich Thorium Vein':255,
            'Adamantite Deposit':325, 'Cobalt Deposit':350,
            'Khorium Vein':375, 'Saronite Deposit':400, 
            'Titanium Vein':450}
            
    herbs = {'Peacebloom':1, 'Silverleaf':1, 'Earthroot':15, 'Mageroyal':50, 
             'Briarthorn':70, 'Stranglekelp':85, 'Bruiseweed':100, 
             'Wild Steelbloom':115, 'Grave Moss':120, 'Kingsblood':125, 
             'Liferoot':150, 'Fadeleaf':160, 'Goldthorn':170, 
             "Khadgar\\'s Whisker":185, 'Wintersbite':195, 'Firebloom':205, 
             'Purple Lotus':210, "Arthas\\' Tears":220, 'Sungrass':230, 
             'Blindweed':235, 'Ghost Mushroom':245, 'Gromsblood':250, 
             'Golden Sansam':260, 'Dreamfoil':270, 'Mountain Silversage':280, 
             'Plaguebloom':285, 'Icecap':290, 'Black Lotus':300, 'Felweed':300, 
             'Dreaming Glory':315, 'Ragveil':325, 'Terocone':325, 
             'Flame Cap':335, 'Goldclover':350, 'Nightmare Vine':365, 
             'Mana Thistle':375, 'Tiger Lily':375, "Talandra\\'s Rose":385, 
             "Adder\\'s Tongue":400, 'Frozen Herb':400, 'Lichbloom':425, 
             'Icethorn':435, 'Frost Lotus':450}
            
    #ores = {'Small Thorium Vein':230} #testbed
    
    curr_resource = ores if resource_type == 'ores' else herbs
    
    db, cursor = open_sql_db(db_user, db_pass)
    
    for k, v in curr_resource.items():
        query = f"SELECT entry FROM gameobject_template WHERE (name LIKE '%{k}%')"
        cursor.execute(query)
        entries = [x[0] for x in cursor.fetchall()]
        resources.append(Resource(k, v, entries))
    
    for resource in resources:
        for entry in resource.entry_id:
            query = 'SELECT guid, id, map, position_x, position_y, position_z ' +\
                    'FROM gameobject WHERE id = ' + str(entry)
            cursor.execute(query)
            results = cursor.fetchall()
            for x in results:
                newnode = Node(*x, resource.name, resource.skill, None, None)
                nodelist.append(newnode)
                
    print(f'{len(nodelist)} node entries read.')
    
    for node in nodelist: # now populate with pool_entry and descriptions
        query = 'SELECT pool_entry, description FROM pool_gameobject WHERE ' +\
                'guid = ' + str(node.guid)
        cursor.execute(query)
        results = cursor.fetchall()
        if results:
            node.pool, node.desc = results[0][0], results[0][1]
            
    cursor.close()
            
    nodelist = sorted(nodelist, key=lambda x:x.skill)
    return nodelist

def main():
    db_user = 'root' # for local AzCore world DB, change as needed
    db_pass = 'password'
    nodelist = import_sql_node_data(db_user, db_pass, 'ores')
    found = brute_nodesearch(nodelist, 3)
    export_results('azcore-duplicate-nodes.txt', found)

if __name__ == '__main__':
    main()
