# SWS-RDP

## Simple Web Server with Reliable Datagram Protocol Transceiver
 
SoR is bidirectional with data flows between sor-client and sor-server for request response applications. Unlike the TCP socket, SoR flexibly establishes the RDP connection and sends the HTTP request in one packet. If the RDP-PAYLOAD is larger than what SoR accomodates, the connection is reset with RST, and the user must rerun sor-client with a smaller RDP-PAYLOAD.

HTTP packet PAYLOAD is a maximum of 1024 bytes, so if the requested file(s) is/are longer than 1024 bytes, the requested file(s) will be segmented into multiple HTTP-PAYLOAD segments encapsulated in many RDP packets. Which is regulated by flow and error control. 

Both the sor-client and sor-server can close the RDP connection via sending an RDP packet that contains FIN. The connetion is fully closed after the other party's FIN command is acknowledged. In an ideal case with a small enough request and response, SWS-RDP can finalize the transaction in 1 RTT and 3 packets. 

## Server Usage

***python3 sor-server.py *server_ip server_udp_port server_buffer_size server_payload_length****

## Client Usage

***python3 sor-client.py *server_ip server_udp_port client_buffer_size client_payload_length readfile_name write_filename ([readfile writefile])****
