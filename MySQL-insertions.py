#!/usr/bin/python3
import netsnmp
import sys
import ipaddress
import textwrap
import MySQLdb

######################################## MAIN ########################################
# Main program: Using the IP given as an argument when calling the script, inserting 
# the IP and model name into the table "unit", then insert its corresponding
# interface-data into the table "interfaces". 
# NOTE: If IP is already in the table; remove the existing one and insert a new entry.
def main():

    # If IP-entry already exists: delete existing row.
    cursor.execute("SELECT EXISTS(SELECT ip_address FROM unit WHERE ip_address = %s)", (ip,))
    if cursor.fetchone()[0] == 1:
        secureExecute("DELETE FROM unit WHERE ip_address = %s", (ip,))

    # Insert a unit record into the table "unit".
    secureExecute("INSERT INTO unit(ip_address, name, model) VALUES(%s, %s, %s)", 
                  (str(ip), get(netsnmp.Varbind("sysName", 0)), getNext("mib-2.47.1.1.1.1.13")))
    
    # Insert matching interfaces from the unit of the previous insertion, into the table "interface".
    foreignKey = int(cursor.lastrowid)   
    listOfLists = listIfInfo()
    for ifList in listOfLists:
        secureExecute("INSERT INTO interface(unit_id, ip_address, mask, name, mac_address) VALUES(%s, %s, %s, %s, %s)",
                      (foreignKey, ifList[0], ifList[1], ifList[2], ifList[3]))
    # Clean up.
    db.commit()
    cursor.close()
    db.close()


######################################## FUNCTIONS ####################################
# Perform a secure cursor execute (catching and listing exceptions, then exit the program with an attached clean up).
def secureExecute(argStr, argValue):
    try:
        cursor.execute(argStr, argValue)
    except Exception as ex:
        print(f"Exception error while performing database query: {ex}")
        cursor.close()
        db.close()
        sys.exit(3)


# Check: Valid IP address.
def validateIP(ipaddr):
    try:
        return str(ipaddress.IPv4Address(ipaddr))
    except:
        print("You have entered an invalid IP address.")
        sys.exit(2)


# Check: Number of arguments.
def validateNumArg(numArg, errorMessage):
    if len(sys.argv) != numArg + 1:
        print(errorMessage)
        sys.exit(1)


#Get index number from interface IP address
def ipAddr_ifIndex(ipaddr):
    OID = netsnmp.Varbind('ipAdEntIfIndex.'+ipaddr)
    int_index = netsnmp.snmpget(OID, Version = 2, DestHost = ip, Community = community)

    return int_index[0].decode('utf8')


#Get mac address. ifPhysAddress stores content in in hexadecimal
def mac(ipaddr):
    int_index = str(ipAddr_ifIndex(ipaddr))

    OID = netsnmp.Varbind('ifPhysAddress.'+int_index)
    add_phy = netsnmp.snmpget(OID, Version = 2, DestHost = ip, Community = community)
    phys = add_phy[0].hex()

    if len(phys) != 12:
        add_phys = 'N\A'
    else:
        tmp=textwrap.wrap(phys,2)
        add_phys=':'.join(tmp)

    return add_phys


# Failsafe utf8-decoding of the incoming argument.
def decode(arg):
    try:
        return arg.decode('utf8')
    except:
        return "Decoding of the argument was unsuccessful." 


# Perform an SNMP-get-request and return a decoded string of the respons.
def get(oid):
    respons = netsnmp.snmpget(
        oid, 
        Version = 2, 
        DestHost = ip, 
        Community = community,
        Timeout = timeout, 
        Retries = retries)

    if respons[0] == None:
        return "No SNMP-respons."
    else:
        return decode(respons[0])    


# Perform an SNMP-getnext-request and return a decoded string of the respons.
def getNext(oid):
    respons = netsnmp.snmpgetnext(
        oid, Version = 2, 
        DestHost = ip, 
        Community = community,               
        Timeout = timeout, 
        Retries = retries)

    if respons[0] == None:
        return "No SNMP-respons."
    else:
        return decode(respons[0])

# Perform an SNMP-walk-request, utf8-decode the extracted elements and finally print the 
# entire tuple with the argument "elemPerRow" number of elements per row.
def printWalk(oid, elemPerRow):
    respons = netsnmp.snmpwalk(
        oid, Version = 2, 
        DestHost = ip, 
        Community = community,                        
        Timeout = timeout, 
        Retries = retries)

    if len(respons) == 0:
        print("No SNMP-respons.", end='')
        return -1
    
    # Print the entire tuple.
    for x in range(0, len(respons)):
        if x == (len(respons) - 1):
            print(decode(respons[x]), end='')
        else:
            print(f'{decode(respons[x])}, ',  end='')
        if ((x + 1) % elemPerRow) == 0 and x != 0:
            print('')

    return 0


# Return a list of lists containing interface information chained to the IP given as an 
# argument when the script is called. The table will consist of the IP-address, netmask, 
# interface and MAC-address of the targeted machine.
def listIfInfo():
    ipAdEntAddr = netsnmp.snmpwalk(
        "ipAdEntAddr", 
        Version = 2, 
        DestHost = ip, 
        Community = community,                            
        Timeout = timeout, 
        Retries = retries)

    if len(ipAdEntAddr) == 0:
        print("No SNMP-respons.")
        return -1

    listOfLists = []

    for ipAddress in ipAdEntAddr:
        cycleList = []
        currentIP = decode(ipAddress)
        cycleList.append(currentIP)
        cycleList.append(get(netsnmp.Varbind("ipAdEntNetMask." + currentIP)))
        cycleList.append(get(netsnmp.Varbind("ifDescr." + ipAddr_ifIndex(currentIP))))
        cycleList.append(mac(currentIP))
        listOfLists.append(cycleList)

    return listOfLists


######################################## CLASSES ########################################
# Logging output to files.
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open(ip + ".txt", "w")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        #For Python3 compability.
        pass


######################################## INITIALIZATION #################################
# Check: Number of arguments.
validateNumArg(2, "You must enter two arguments (community and IP-address, respectively).")

# Check / Set: Valid IP address and make the variable "ip" globally usable.
ip = validateIP(sys.argv[2])

# Set: community string to be used throughout every SNMP-request.
community = sys.argv[1]

# Extra options made with every SNMP-request
timeout = 50000
retries = 0

# Connection to database.
db = MySQLdb.connect("localhost", "root", "#netadm06!", "my_network")
cursor = db.cursor()

# Enables logging of the coming output.
#sys.stdout = Logger()

# Start the program.
main()
