import socket
from datetime import datetime
import sys
import os
import pickle
import re

ClientAddress = ()
ServerIP = 'h2'
ServerPort = 8888

BUFFER_SIZE = 4096
RDP_PAYLOAD = 1024

SequenceNum = 0
Length = 0
Ack = 1
Window = 4096
Response = ''

ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def getInputs(inputArgs):
    global ServerIP, ServerPort, BUFFER_SIZE, MAX_PAYLOAD, Window, ServerSocket

    ServerIP = inputArgs[1]
    ServerPort = int(inputArgs[2])
    BUFFER_SIZE = int(inputArgs[3])
    MAX_PAYLOAD = int(inputArgs[4])
    ServerSocket.bind((ServerIP, ServerPort))
    Window = BUFFER_SIZE


def sendMSG(headerInfo, httpRequest, address):
    
    msg = headerInfo[0] + '\nSequence: ' + str(headerInfo[1]) + '\nLength: ' + str(headerInfo[2]) + '\nAcknowledgment: ' + str(headerInfo[3]) + '\nWindow: ' + str(headerInfo[4]) + '\n'

    message = [msg, httpRequest]
    message = pickle.dumps(message)

    ServerSocket.sendto(message, address)

def recvFrom():
    
    data, addr = ServerSocket.recvfrom(BUFFER_SIZE)
    data = pickle.loads(data)

    t = []
    entry = re.split("\n", data)
    for e in entry:
        cmd = re.split(": ", e)
        if len(cmd) == 2:
            t.append(cmd[1])
        elif cmd[0] != '':
            t.append(cmd[0])
    
    t[1] = int(t[1])    # SequenceNum
    t[2] = int(t[2])    # Length
    t[3] = int(t[3])    # Ack
    t[4] = int(t[4])    # Window
                        # GET /filename HTTP/1.0
                        # keep-alive or closed
    return (t, addr)

class responsePkts:
    pkt_storage = []

class Pkt:
    pkt_storage = []
    header = ''
    firstPkt = True
    pktNum = 0
    segmentSize = 982

    def getPktSegment(self, file):
        while 1:
            if self.firstPkt:
                self.segmentSize = MAX_PAYLOAD - len(self.header)
                self.firstPkt = False
            else:
                self.segmentSize = MAX_PAYLOAD
            data = file.read(self.segmentSize)
            if not data:
                break
            yield data

    def readFile(self, filename):
        #print("In readFile")
        with open(filename, 'r') as f:
            for chunk in self.getPktSegment(f):
                self.pkt_storage.append(chunk)
            self.pktNum = len(self.pkt_storage)
    
def makeDataPkt(inputFile, header):
    pktStorage = Pkt()
    pktStorage.header = header
    pktStorage.pkt_storage = []
    pktStorage.readFile(inputFile)
    
    return pktStorage

def makePkts(inputFile, connectionType):
    global ClientAddress, Response

    try: 
        currHeader = '\nHTTP/1.0 200 OK\nConnection: ' + connectionType + '\n'
        pktStorage = makeDataPkt(inputFile, currHeader)
        pktStorage.pkt_storage[0] = currHeader + pktStorage.pkt_storage[0]
        Response = 'HTTP/1.0 200 OK'
        
        return pktStorage
    
    except FileNotFoundError:
        pktStorage = responsePkts()
        responseMSG = '\nHTTP/1.0 404 Not Found\nConnection: ' + connectionType + '\n'
        pktStorage.pkt_storage.append(responseMSG)
        pktStorage.pkt_storage.append('FNF')
        Response = 'HTTP/1.0 404 Not Found'
    
        return pktStorage


def sendPkts(data, pktStorage):
    global ClientAddress, SequenceNum, Length, Ack, Window
    currPkt = 0
    ackPkts = []

    ackPkts.append(data)
    Ack += data[2]
    Length = len(pktStorage.pkt_storage[currPkt])
    rdpHeader = ['ACK|SYN|DAT', SequenceNum, Length, Ack, Window]
    sendMSG(rdpHeader, pktStorage.pkt_storage[currPkt], ClientAddress)


    while 1:
        currPkt = len(ackPkts)

        try:
            data, addr = recvFrom()
        except:
            continue

        if len(ackPkts) == 1 and data[0] == 'SYN|DAT|ACK':
            Length = MAX_PAYLOAD
            currPkt = 0
            rdpHeader =  ['ACK|SYN|DAT', SequenceNum, Length, Ack, Window]
            sendMSG(rdpHeader, pktStorage.pkt_storage[currPkt], ClientAddress)

        elif data[0] == 'ACK' and pktStorage.pkt_storage[1] == 'FNF':
            SequenceNum = data[3]
            Length = 0
            rdpHeader = ['FIN|ACK', SequenceNum, Length, Ack, Window]
            sendMSG(rdpHeader, '', ClientAddress)

        elif data[4] >= MAX_PAYLOAD and data[0] == 'ACK':
            if data not in ackPkts:
                ackPkts.append(data)
            else:
                currPkt -= 1

            if currPkt < pktStorage.pktNum:
                SequenceNum = data[3]
                Length = len(pktStorage.pkt_storage[currPkt])
                rdpHeader = ['ACK|DAT', SequenceNum, Length, Ack, Window]
                sendMSG(rdpHeader, pktStorage.pkt_storage[currPkt], ClientAddress)

            else:
                SequenceNum = data[3]
                Length = 0
                rdpHeader = ['FIN|ACK', SequenceNum, Length, Ack, Window]
                sendMSG(rdpHeader, '', ClientAddress)
            
        elif data[0] == 'FIN|ACK':
            ackPkts.append(data)
            SequenceNum = data[3]
            Ack += 1
            Length = 0
            rdpHeader = ['ACK', SequenceNum, Length, Ack, Window]
            
            # Make sure we send the last ACK and it is received properly
            x = 0
            while x < 5:
                sendMSG(rdpHeader, '', ClientAddress)
                x += 1
            
            SequenceNum += 1
            break


def handleKeepAlive():
    global Ack
    data, addr = recvFrom()
    Ack = data[3] + 2
    handleRequest(data, addr)

def handleRST():
    global SequenceNum, Length, Ack, Window, BUFFER_SIZE

    SequenceNum = 0
    Length = 0
    Ack = 1
    Window = BUFFER_SIZE


def handleRequest(data, addr):
    global Length, ClientAddress
    
    ClientAddress = addr

    if data[0] == 'SYN|DAT|ACK':
        Length = data[2]
    else:
        handleBadRequest()
    
    httpRequest = data[5]
    correctHTTP = re.compile(r"((GET) \/(.*) (HTTP/1.0))")
    # Full Regex: r"((GET) \/(.*) (HTTP/1.0))(\S+$)"
    # Match 1: GET /filename HTTP/1.0\n
    # Group 1: GET /filename HTTP/1.0
    # Group 2: GET
    # Group 3: filename
    # Group 4: HTTP/1.0
    # Group 5: \n

    aliveorClosed = data[6]
    correctAliveOrClosed = re.compile(r"\w+\S+", re.I)  # Case-insensitive
    # Full Regex: r"\w+\S+"
    # If alive:
        # Match 1: keep-alive
    # If closed:
        # Match 1: closed
    # Potential Regex: r"(.*)(\\n)"
    # If alive:
        # Match 1: Connection: keep-alive\n
        # Group 1: Connection: keep-alive
        # Group 2: \n
    # If closed:
        # Match 1: Connection: closed\n or closed\n
        # Group 1: Connection: closed or closed
        # Group 2: \n
    
    httpMatch = correctHTTP.match(httpRequest)
    statusMatch = correctAliveOrClosed.match(aliveorClosed)
    if not httpMatch:
        handleBadRequest()
    elif statusMatch:
        inputFile = httpMatch.group(3)
        pktStorage = makePkts(inputFile, aliveorClosed)
        printConnectionStatus(data)
        try:
            sendPkts(data, pktStorage)
        except:
            os._exit()
        
        if statusMatch == 'keep-alive':
            handleKeepAlive()
            return
        else:   # Connection is closed
            return
    

def handleBadRequest():
    Response = "\nHTTP/1.0 400 Bad Request\n"
    
    print(Response)
    os._exit(0)

def printConnectionStatus(data):
    global Response

    currTime = datetime.now()
    timeStamp = currTime.strftime("%a %b %d %H:%M:%S PST 2021")

    msg = timeStamp + ": " + str(ClientAddress[0]) + ":" + str(ClientAddress[1]) + " " + str(data[5]) + "; " + Response

    print(msg)
    

def serverMain():
    
    while 1:
        data, address = recvFrom()
        
        try:
            handleRequest(data, address)
        except:
            handleRST()
            break
            

if __name__ == '__main__':
    getInputs(sys.argv)
    serverMain()