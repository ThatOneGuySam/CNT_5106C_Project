import sys
import os
import math
import socket
import select
import time
import logging

class PeerProcess():
    def __init__(self, id: int, host_name: str, port: int, has_file: bool,
                 num_pref_nbors: int, unchoke_int: int, opt_unchoke_int: int, file_name: str,
                 file_size: int, piece_size: int, next_peers):
        self.id = id
        self.host_name = host_name
        self.port = port
        self.has_file = has_file
        
        self.numPrefNbors = num_pref_nbors
        self.unchoke_int = unchoke_int
        self.opt_unchoke_int = opt_unchoke_int
        self.file_name = file_name
        self.file_size = file_size
        self.piece_size = piece_size
        
        self.subdir = f"{os.getcwd()}/peer_{str(self.id)}"
        if not os.path.exists(self.subdir):
            os.mkdir(self.subdir)

        self.num_pieces = int(math.ceil(file_size/piece_size))
        self.num_pieces_held = 0

        self.bitfield = self.initialize_bitfield(self.has_file)
        self.full_bitfield = self.initialize_bitfield(True) #For easy comparison purposes
        self.empty_bitfield = self.initialize_bitfield(False) #For easy comparison purposes
        self.pieces = self.initialize_pieces(self.has_file, self.piece_size, self.num_pieces)
        self.peers_with_whole_file = 0
        if self.has_file:
            self.peers_with_whole_file += 1
            self.num_pieces_held = self.num_pieces
        self.next_peers = next_peers
        
        self.peers_info = dict()
        self.connections = dict()
        #List form used for reading from sockets
        self.sockets_list = list()
        self.listening_socket = self.initialize_socket(host_name, port)

        self.all_requests = list()

        logging.basicConfig(level=logging.INFO,  # Set the log level
                    format='%(asctime)s : %(message)s',  # Set the log format
                    handlers=[logging.FileHandler(f'log_peer_{self.id}.log')])
        
        
    def initialize_bitfield(self, has_file: bool):
        length = math.ceil(self.num_pieces / 8) * 8
        remainder = (8 - (self.num_pieces % 8)) % 8
        if has_file:
            #Set all bits to one except remainder
            bitfield = '1'*(length-remainder) + '0'*(remainder)
        else:
            bitfield = '0'*(length)
        bitfield_int = int(bitfield,2)
        return bytearray(bitfield_int.to_bytes(length // 8, byteorder='big'))
    
    def initialize_pieces(self, has_file: bool, piece_size: int, num_pieces: int):
        return dict({i: has_file for i in range(num_pieces)})

    def initialize_socket(self, host_name: str, port: int):
        curr_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        curr_socket.bind((host_name, port))
        curr_socket.listen(len(self.next_peers))
        return curr_socket
    
    def make_handshake_header(self, peer_id: int):
        initial_header = "P2PFILESHARINGPROJ".encode('utf-8')
        zero_bytes = bytearray(10)
        identifier = peer_id.to_bytes(4, byteorder = 'big')
        full_header = initial_header + zero_bytes + identifier
        return full_header

    def add_peer(self, peer):
        self.peers_info[peer.peer_id] = peer
        self.peers_info[peer.peer_id].bitfield = self.initialize_bitfield(False)
        self.peers_info[peer.peer_id].interesting_pieces = self.initialize_bitfield(False)
        try:
            self.connections[peer.peer_id] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connections[peer.peer_id].connect((peer.host_name, peer.port_num))
            logging.info(f"Peer {self.id} makes a connection to Peer {peer.peer_id}")
            self.connections[peer.peer_id].send(self.make_handshake_header(self.id))
            answer = self.connections[peer.peer_id].recv(1024)
            print(answer)
            if answer != self.make_handshake_header(peer.peer_id):
                raise ConnectionError("Unexpected header, something with the connection has failed")
            if self.bitfield != self.empty_bitfield:
                self.send_message(peer.peer_id, 5, self.bitfield)
        except ConnectionError as e:
            print(e)
            del self.peers_info[peer.peer_id]
            del self.connections[peer.peer_id]
            return None

    def wait_for_connection(self):
        conn, addr = self.listening_socket.accept()
        try:
            header = conn.recv(1024)
            print(header)
            byte_conn_id = header[-4:]
            conn_id = int.from_bytes(byte_conn_id, "big")
            if conn_id != self.next_peers[0].peer_id:
                raise ConnectionError("Header has an incorrect peer id")
            curr_peer = self.next_peers[0]
            logging.info(f"Peer {self.id} is connected from Peer {curr_peer.peer_id}")
            self.peers_info[curr_peer.peer_id] = curr_peer
            self.peers_info[curr_peer.peer_id].bitfield = self.initialize_bitfield(False)
            self.peers_info[curr_peer.peer_id].interesting_pieces = self.initialize_bitfield(False)
            self.connections[curr_peer.peer_id] = conn
            self.next_peers.remove(curr_peer)
            self.connections[curr_peer.peer_id].send(self.make_handshake_header(self.id))
            if self.bitfield != self.empty_bitfield:
                self.send_message(curr_peer.peer_id, 5, self.bitfield)
        except ConnectionError as e:
            print(e)

    def send_message(self, peer_id: int, msg_type: int, data = None):
        if data:
            send_length = (len(data)+1).to_bytes(4, byteorder='big')
        else:
            send_length = (1).to_bytes(4, byteorder='big')
        send_type = msg_type.to_bytes(1, byteorder='big')
        message = send_length + send_type
        if data:
            message = message + data
        self.connections[peer_id].sendall(message)

    def read_message(self, peer_id: int, message):
        #Kill line: If you want to test the program up to a certain point and then have it cleanly stop,
        #Copy the following line at the end of said process
        #self.peers_with_whole_file = len(self.connections) +1
        msg_length = int.from_bytes(message[0:4], byteorder='big')
        msg_type = int.from_bytes(message[4:5], byteorder='big')
        msg_data = None
        if msg_length > 1:
            msg_data = message[5:]
        try:
            if msg_data and len(msg_data)+1 != msg_length:
                raise ValueError("Message data is not given length")
            match msg_type:
                case 0:
                    #TODO: Message is choke
                    print("RUNNING CASE 0")
                    return None
                case 1:
                    #TODO: Message is unchoke
                    print("RUNNING CASE 1")
                    return None
                case 2:
                    #TODO: Message is interested
                    print("RUNNING CASE 2")
                    logging.info(f"Peer {self.id} received the \'interested\' message from Peer {peer_id}")
                    self.peers_info[peer_id].interested_in_me = True
                    #Commented out functions useful for testing piece sending
                    #if self.id == 1001:
                    #    for piece in range(self.num_pieces):
                    #        self.send_message(peer_id, 7, self.package_piece(piece))
                    #self.send_message(peer_id, 7, self.package_piece(0))
                case 3:
                    #TODO: Message is not interested
                    print("RUNNING CASE 3")
                    logging.info(f"Peer {self.id} received the \'not interested\' message from Peer {peer_id}")
                    self.peers_info[peer_id].interested_in_me = False
                    return None
                case 4:
                    #TODO: Message is have
                    print("RUNNING CASE 4")
                    piece_index = int.from_bytes(msg_data, byteorder='big')
                    logging.info(f"Peer {self.id} received the \'have\' message from Peer {peer_id} for the piece {piece_index}")
                    piece_byte = piece_index // 8
                    piece_bit = piece_index % 8
                    tick_mark = (1 << (7 - piece_bit))
                    self.peers_info[peer_id].bitfield[piece_byte] =  self.peers_info[peer_id].bitfield[piece_byte] | tick_mark
                    if self.peers_info[peer_id].bitfield == self.full_bitfield:
                        print("Addition: friend")
                        self.peers_with_whole_file += 1
                    if not bool(self.bitfield[piece_byte] & tick_mark):
                        uninterested_before = self.peers_info[peer_id].interesting_pieces == self.empty_bitfield
                        self.peers_info[peer_id].interesting_pieces[piece_byte] =  self.peers_info[peer_id].interesting_pieces[piece_byte] | tick_mark
                        if uninterested_before:
                            self.send_message(peer_id, 2)
                case 5:
                    #Message is bitfield
                    print("RUNNING CASE 5")
                    if len(msg_data) != len(self.peers_info[peer_id].bitfield):
                        raise ValueError("Provided Bitfield is Incorrect Size")
                    self.peers_info[peer_id].bitfield = msg_data
                    if msg_data == self.full_bitfield:
                        self.peers_with_whole_file += 1
                    interested = False
                    for byte in range(len(msg_data)):
                        for bit in range(8):
                            in_msg_data = bool(msg_data[byte] & (1 << (7 - bit)))
                            out_bitfield = not bool(self.bitfield[byte] & (1 << (7 - bit)))
                            if in_msg_data and out_bitfield:
                                interested = True
                                tick_mark = (1 << (7 - bit))
                                self.peers_info[peer_id].interesting_pieces[byte] = self.peers_info[peer_id].interesting_pieces[byte] | tick_mark
                    if interested:
                        self.send_message(peer_id, 2)
                    else:
                        self.send_message(peer_id, 3)
                    print(self.peers_info[peer_id].interesting_pieces)
                        
                case 6:
                    #TODO: Message is request
                    print("RUNNING CASE 6")
                    try:
                        piece_index = int.from_bytes(msg_data, byteorder="big")
                        piece_byte = piece_index // 8
                        piece_bit = piece_index % 8
                        tick_mark = 1 << (7 - piece_bit)
                        if not bool(self.bitfield[piece_byte] & tick_mark):
                            raise ValueError("Requested piece is not in this peer")
                        self.send_message(peer_id, 7, self.package_piece(piece_index)) 
                    except ValueError as e:
                        print(e)
                case 7:
                    #TODO: Message is piece
                    print("RUNNING CASE 7")
                    piece_index = int.from_bytes(msg_data[0:4], byteorder="big")
                    piece_byte = piece_index // 8
                    piece_bit = piece_index % 8
                    tick_mark = 1 << (7 - piece_bit)
                    if bool(self.bitfield[piece_byte] & tick_mark):
                        raise ValueError("Received a piece this peer already has")
                    piece_data = msg_data[4:]
                    with open(f"{self.subdir}/partial_piece_{piece_index}_{self.file_name}", "wb") as file_bytes:
                        file_bytes.write(piece_data)
                    self.pieces[piece_index] = True
                    self.num_pieces_held += 1
                    logging.info(f"Peer {self.id} has downloaded the piece {piece_index} from {peer_id}. Now the number of pieces it has is {self.num_pieces_held}")
                    self.bitfield[piece_byte] = self.bitfield[piece_byte] | tick_mark
                    self.check_for_completion()
                    for peer in self.connections.keys():
                        self.send_message(peer, 4, (piece_index).to_bytes(4, byteorder="big"))
                        before = self.peers_info[peer].interesting_pieces.copy()
                        self.peers_info[peer].interesting_pieces[piece_byte] = self.peers_info[peer].interesting_pieces[piece_byte] & ~tick_mark
                        if before != self.empty_bitfield and self.peers_info[peer].interesting_pieces == self.empty_bitfield:
                            self.send_message(peer, 3)

                        time.sleep(0.1)

                case _:
                    #Message is unexpected value
                    raise ValueError("Unexpected Message Type")
        except ValueError as e:
            print(e)

    def check_for_completion(self):
        if self.bitfield == self.full_bitfield:
            self.peers_with_whole_file += 1
            print("Addition: Self")
            try:
                with open(f"{self.subdir}/{self.file_name}", "wb") as file_bytes:
                    for index in range(self.num_pieces):
                        if not self.pieces[index]:
                            raise RuntimeError("Peer should not be assembling file at current moment")
                        with open(f"{self.subdir}/partial_piece_{index}_{self.file_name}", "rb") as partial_p:
                            file_bytes.write(partial_p.read())
                        os.remove(f"{self.subdir}/partial_piece_{index}_{self.file_name}")
                logging.info(f"Peer {self.id} has downloaded the complete file.")
            except RuntimeError as e:
                print(e)

    def package_piece(self, piece_index):
        index_bytes = piece_index.to_bytes(4, byteorder='big')
        msg_data = None
        try:
            if os.path.exists(f"{self.subdir}/{self.file_name}"):
                #Straight from file
                with open(f"{self.subdir}/{self.file_name}", "rb") as file_bytes:
                    file_bytes.seek(piece_index*self.piece_size)
                    msg_data = file_bytes.read(self.piece_size)
            elif os.path.exists(f"{self.subdir}/partial_piece_{piece_index}_{self.file_name}"):
                #From partial file
                with open(f"{self.subdir}/partial_piece_{piece_index}_{self.file_name}", "rb") as file_bytes:
                    msg_data = file_bytes.read()
            else:
                raise FileNotFoundError(f"Peer is trying to send piece {piece_index} but does not have it")
        except FileNotFoundError as e:
            print(e)
        message = index_bytes + msg_data
        return message
            

class PeerInfo():
    def __init__(self, peer_id, host_name, port_num, has_file):
        self.peer_id = int(peer_id)
        self.host_name = host_name
        self.port_num = int(port_num)
        self.has_file = has_file == '1'
        self.bitfield = None
        self.interesting_pieces = None
        self.interested_in_me = False






def main():
    if len(sys.argv) < 2:
        raise SyntaxError("Need to provide a peer ID argument")
    id = int(sys.argv[1])
    host_name = None
    port = None
    prev_peers = list()
    next_peers = list()
    #Get previous peers and this peer's port number
    with open('PeerInfo.cfg', 'r') as file:
        for line in file:
            words = line.split()
            if len(words) != 4:
                raise ValueError(f"Peer incorrectly identified for line {line}")
            if int(words[0]) == id and port:
                raise ValueError(f"Peer incorrectly appears multiple times")
            if int(words[0]) == id:
                host_name = words[1]
                port = int(words[2])
                has_file = words[3] == '1'
            elif not port:
                prev_peers.append(PeerInfo(*words))
            else:
                next_peers.append(PeerInfo(*words))
    #If peer never found, throw error
    if not port:
        raise ValueError("Given Peer ID was not found in PeerInfo.cfg file")
    #Now Reading Common file and Setting values
    with open('Common.cfg', 'r') as file:
        #I'm going to get a little overcomplicated here, but I want to be prepared
        #for the case where the config file is given if a different order.
        for line in file:
            words = line.split()
            if len(words) == 0:
                continue
            elif len(words) == 1:
                raise ValueError(f"Missing variable for line {line}")
            key = words[0]
            val = words[1]
            match key:
                case 'NumberOfPreferredNeighbors':
                    num_pref_nbors = int(val)
                case 'UnchokingInterval':
                    unchoke_int = int(val)
                case 'OptimisticUnchokingInterval':
                    opt_unchoke_int = int(val)
                case 'FileName':
                    file_name = val
                case 'FileSize':
                    file_size = int(val)
                case 'PieceSize':
                    piece_size = int(val)
                case _:
                    raise ValueError(f"Unrecognized key: {key}")
    #Initializing PeerProcess
    peer = PeerProcess(id, host_name, port, has_file, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size, next_peers)
    #Now make the previous connections
    for prev_peer in prev_peers:
        peer.add_peer(prev_peer)
    #Now set up acceptance for other connections
    while len(peer.next_peers) > 0:
        peer.wait_for_connection()

    print("We made it")

    peer.sockets_list = list(peer.connections.values())
    num_peers = len(peer.connections) + 1 #Including itself, otherwise last one gets shut out
    MAX_MSG_SIZE = peer.piece_size + 4 + 4 + 1 #Writing it expanded for clarity
    while peer.peers_with_whole_file < num_peers:
        # Use select to check for readable sockets (those with incoming messages)
        read_sockets, _, _ = select.select(peer.sockets_list, [], [])
        
        for sock in read_sockets:
            # Receive the message from the socket
            message = sock.recv(MAX_MSG_SIZE)
            if message:
                # Find the ID corresponding to the socket that sent the message
                peer_id = None
                for key, connection in peer.connections.items():
                    if connection == sock:
                        peer_id = key
                        break
                peer.read_message(peer_id, message)

    for conn in peer.connections.values():
        conn.close()
    peer.listening_socket.close()


if __name__ == "__main__":
    main()