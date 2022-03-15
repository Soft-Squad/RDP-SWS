import socket
from datetime import datetime
import sys
import os
import pickle
import re

ServerIP = 'h2'
ServerPort = 8888
BUFFER_SIZE = 4096
MAX_PAYLOAD = 1024
Files = []
FilesIndex = 0

ACTIVE = True
PktLost = False

SequenceNum = 0
Length = 0
Ack = -1
Window = 4096
NextSequence = 0


clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
clientSocket.settimeout(0.5)


def getInputs(inputArgs):
    global ServerIP, ServerPort, BUFFER_SIZE, MAX_PAYLOAD, Files, ACTIVE, PktLost, Window

    if not len(inputArgs) % 2 != 0:
        print("Missing Input Arguments")
        ACTIVE = False
        return

    try:
        PktLost = False    
        ServerIP = inputArgs[1]
        ServerPort = int(inputArgs[2])
        BUFFER_SIZE = int(inputArgs[3])
        MAX_PAYLOAD = int(inputArgs[4])
        Window = BUFFER_SIZE
        for i in range(5, len(inputArgs)):
            Files.append(inputArgs[i])
    
    except:
        print("Missing Input Arguments")
        ACTIVE = False
        return


def sendMSG(headerInfo, httpRequest, address):
    
    msg = headerInfo[0] + '\nSequence: ' + str(headerInfo[1]) + '\nLength: ' + str(headerInfo[2]) + '\nAcknowledgment: ' + str(headerInfo[3]) + '\nWindow: ' + str(headerInfo[4]) + '\n'

    message = msg + httpRequest
    message = pickle.dumps(message)
    

    clientSocket.sendto(message, address)

def recvFrom():
    
    data, addr = clientSocket.recvfrom(BUFFER_SIZE)
    data = pickle.loads(data)

    t = []
    entry = re.split("\n", data[0])
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
    t.append(data[1])
    
    
    return (t, addr)

def printMSGSent(header):
   
    currTime = datetime.now()
    timeStamp = currTime.strftime("%a %b %d %H:%M:%S PST %Y")
    msg = timeStamp + ': '+'Send; '+ header[0] + '; Sequence: ' + str(SequenceNum) + '; Length: ' + str(Length) + '; Acknowledgment: ' + str(Ack) + '; Window: ' + str(Window)
    
    print(msg)
    
def writeToFile(data):
    with open(Files[FilesIndex + 1], '+a') as f:
        f.write(data)
        f.close

def printMSGRecieved(header):
    
    currTime = datetime.now()
    timeStamp = currTime.strftime("%a %b %d %H:%M:%S PST %Y")
    msg = timeStamp + ': ' + 'Receive; ' + header[0] + '; Sequence: '+ str(header[1]) + '; Length: ' + str(header[2]) + '; Acknowledgment: ' + str(header[3]) + '; Window: ' + str(header[4])
    print(msg)

def clientServer():
    global ServerIP, ServerPort, Files, FilesIndex, ACTIVE, PktLost, SequenceNum, Length, Ack, Window, NextSequence

    serverAddress = (ServerIP, ServerPort)
    connected = False
    pktsReceived = []
    firstPkt = True
    confirmedPkts = []
    buffer = 0
    lastPkt = 0
    serverComplete = False
    noFile = False
    currWindow = (BUFFER_SIZE / MAX_PAYLOAD) - 2
    
    filesPos = FilesIndex + 2
    if filesPos != len(Files):
        connectionStatus = 'keep-alive'
    else:
        connectionStatus = 'closed'
    
    while connected == False:

        fileRequests = len(Files) - 1
        if FilesIndex < fileRequests:
            httpRequest = '\nGET /' + Files[FilesIndex] + ' HTTP/1.0\nConnection: ' + connectionStatus + '\n'

        Length = len(httpRequest)
        rdpHeader = ['SYN|DAT|ACK', SequenceNum, Length, Ack, Window]
        sendMSG(rdpHeader, httpRequest, serverAddress)

        if PktLost == False:
            printMSGSent(rdpHeader)
        connected = True

    while 1:
        try:
            data, addr = recvFrom()

            if firstPkt == True and data[0] == 'ACK':
                continue
            PktLost = False
            printMSGRecieved(data)
        
        except socket.timeout:     # Timeout value reached
            PktLost = True
            if len(pktsReceived) == 0:
                return
            data = pktsReceived[-1]

        if data[0] == 'ACK|DAT' or data[0] == 'ACK|SYN|DAT':
            serverResponse = data[5][:50]
            
            if '404 Not Found' in serverResponse:
                noFile = True
            
            if firstPkt:
                x = 30 + len(connectionStatus)
                data[5] = data[5][x:]
                firstPkt = False
            
            if data[1] == NextSequence and data[5] not in confirmedPkts:
                pktsReceived.append(data)
                buffer += 1
                NextSequence = data[1] + data[2]
            
            else:
                PktLost = True
                data = pktsReceived[-1]
            
            if buffer > currWindow:
                for i in range(lastPkt, len(pktsReceived)):
                    writeToFile(pktsReceived[i][5])
                    lastPkt += 1
                    confirmedPkts.append(pktsReceived[i][5])
                Window = BUFFER_SIZE
                buffer = 0
            
            Ack = data[1] + data[2]
            SequenceNum = data[3]
            Length = 0

            if PktLost == False:
                Window -= data[2]
            rdpHeader = ['ACK', SequenceNum, Length, Ack, Window]
            sendMSG(rdpHeader, '', serverAddress)
            if PktLost == False:
                printMSGSent(rdpHeader)

        elif data[0] == 'FIN|ACK':
            if noFile == False:
                if lastPkt < len(pktsReceived):
                    for j in range(lastPkt, len(pktsReceived)):
                        writeToFile(pktsReceived[j][5])
                        lastPkt += 1
                        confirmedPkts.append(pktsReceived[j][5])
                    Window = BUFFER_SIZE
            
            pktsReceived.append(data)
            buffer += 1
            Ack = data[1] + 1
            SequenceNum = data[3]
            Window = BUFFER_SIZE
            Length = 0
            rdpHeader = ['FIN|ACK', SequenceNum, Length, Ack, Window]
            sendMSG(rdpHeader, '', serverAddress)
            serverComplete = True
            printMSGSent(rdpHeader)

        elif data[0] == 'ACK':
            if serverComplete == False:
                continue
            filesPos = FilesIndex + 2
            if filesPos == len(Files):
                clientSocket.close()
                ACTIVE = False
                break
            else:
                FilesIndex += 2
                Ack += 1
                SequenceNum = data[3]
                NextSequence = data[1] + 1
                return


if __name__ == '__main__':
    getInputs(sys.argv)
    while ACTIVE:
        clientServer()
    clientSocket.close()
    os._exit(0)