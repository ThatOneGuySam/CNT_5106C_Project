import sys
import os
import math
import socket
import select
import time
import logging
import threading
import random

class PeerProcess():
    def __init__(self,
                 id: int,
                 host_name: str,
                 port: int,
                 has_file: bool,
                 num_pref_nbors: int,
                 unchoke_int: int,
                 opt_unchoke_int: int,
                 file_name: str,
                 file_size: int,
                 piece_size: int,
                 next_peers):
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

        #Ensure file is in peer
        if self.has_file and not os.path.exists(f"{self.subdir}/{self.file_name}"):
            raise RuntimeError(f"Peer is marked as having file {self.file_name} yet it does not.")

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
        self.socket_lock = threading.Lock()
        self.listening_socket = self.initialize_socket(host_name, port)
        

        self.neighbors_interested = list()
        self.neighbors_choking_me = list()
        self.current_requests = list()

        # TODO: choking and unchoking
        self.download_rates = dict()
        self.preferred_neighbors = set()
        self.optimistically_unchoked_peer = None
        self.unchoke_lock = threading.Lock()
        

        self.timers = list()
        
        self.peer_buffers = dict()
        self.peers_next_length = dict()

        logging.basicConfig(level=logging.INFO,  # Set the log level
                    format='%(asctime)s : %(message)s',  # Set the log format
                    handlers=[logging.FileHandler(f'{self.subdir}/log_peer_{self.id}.log')])
        
    def start_listening(self):
        self.listener_thread = threading.Thread(target=self.wait_for_connection, daemon=True)
        self.listener_thread.start()
        
        
    def initialize_bitfield(self, has_file: bool):
        length = math.ceil(self.num_pieces / 8) * 8
        remainder = (8 - (self.num_pieces % 8)) % 8
        if has_file:
            # Set all bits to one except remainder
            bitfield = '1'*(length-remainder) + '0'*(remainder)
        else:
            bitfield = '0'*(length)
        bitfield_int = int(bitfield,2)
        return bytearray(bitfield_int.to_bytes(length // 8, byteorder='big'))
    
    def initialize_pieces(self, has_file: bool, piece_size: int, num_pieces: int):
        return dict({i: has_file for i in range(num_pieces)})

    def initialize_socket(self, host_name: str, port: int):
        with self.socket_lock:
            try:
                curr_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                curr_socket.bind((host_name, port))
                curr_socket.listen(len(self.next_peers))
            except ConnectionError as e:
                print("OH, ", e)
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
        self.peers_info[peer.peer_id].interesting_pieces = list()
        self.download_rates[peer.peer_id] = 0
        try:
            self.connections[peer.peer_id] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connections[peer.peer_id].connect((peer.host_name, peer.port_num))
            logging.info(f"Peer {self.id} makes a connection to Peer {peer.peer_id}")
            self.connections[peer.peer_id].send(self.make_handshake_header(self.id))
            answer = self.connections[peer.peer_id].recv(1024)
            if answer != self.make_handshake_header(peer.peer_id):
                raise ConnectionError("Unexpected header, something with the connection has failed")
            if self.bitfield != self.empty_bitfield:
                self.send_message(peer.peer_id, 5, self.bitfield)
        except ConnectionError as e:
            logging.info(f"Error: {e}")
            del self.peers_info[peer.peer_id]
            del self.connections[peer.peer_id]
            return None

    def wait_for_connection(self):
        with self.socket_lock:
            while len(self.next_peers) > 0:
                conn, addr = self.listening_socket.accept()
                try:
                    header = conn.recv(1024)
                    byte_conn_id = header[-4:]
                    conn_id = int.from_bytes(byte_conn_id, "big")
                    if conn_id != self.next_peers[0].peer_id:
                        raise ConnectionError("Header has an incorrect peer id")
                    curr_peer = self.next_peers[0]
                    logging.info(f"Peer {self.id} is connected from Peer {curr_peer.peer_id}")
                    self.peers_info[curr_peer.peer_id] = curr_peer
                    self.peers_info[curr_peer.peer_id].bitfield = self.initialize_bitfield(False)
                    self.peers_info[curr_peer.peer_id].interesting_pieces = list()
                    self.sockets_list.append(conn)
                    self.connections[curr_peer.peer_id] = conn
                    self.peer_buffers[curr_peer.peer_id] = bytearray()
                    self.peers_next_length[curr_peer.peer_id] = 0
                    self.download_rates[curr_peer.peer_id] = 0
                    self.next_peers.remove(curr_peer)
                    self.connections[curr_peer.peer_id].send(self.make_handshake_header(self.id))
                    logging.info(f"Bitfield is {self.bitfield}")
                    if self.bitfield != self.empty_bitfield:
                        logging.info(f"Sending")
                        self.send_message(curr_peer.peer_id, 5, self.bitfield)
                except ConnectionError as e:
                    logging.info(f"Error: {e}")

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
                raise ValueError(f"Message data from {peer_id} is not given length:\n Message type is {msg_type} and length given is {msg_length}, but real length is {len(msg_data)+1}\nMessage is: {message}")
            match msg_type:
                case 0:
                    #Message is choke
                    logging.info(f"Peer {self.id} is choked by {peer_id}")
                    self.neighbors_choking_me.append(peer_id)
                    

                case 1:
                    #Message is unchoke
                    if peer_id in self.neighbors_choking_me:
                        self.neighbors_choking_me.remove(peer_id)
                    logging.info(f"Peer {self.id} is unchoked by {peer_id}")
                    if len(self.peers_info[peer_id].interesting_pieces) != 0:
                        self.find_and_request(peer_id)
                case 2:
                    #Message is interested
                    logging.info(f"Peer {self.id} received the \'interested\' message from Peer {peer_id}")
                    self.peers_info[peer_id].interested_in_me = True
                    self.neighbors_interested.append(peer_id)
                case 3:
                    #Message is not interested
                    logging.info(f"Peer {self.id} received the \'not interested\' message from Peer {peer_id}")
                    self.peers_info[peer_id].interested_in_me = False
                    self.neighbors_interested.remove(peer_id)
                case 4:
                    #Message is have
                    piece_index = int.from_bytes(msg_data, byteorder='big')
                    logging.info(f"Peer {self.id} received the \'have\' message from Peer {peer_id} for the piece {piece_index}")
                    piece_byte = piece_index // 8
                    piece_bit = piece_index % 8
                    tick_mark = (1 << (7 - piece_bit))
                    self.peers_info[peer_id].bitfield[piece_byte] =  self.peers_info[peer_id].bitfield[piece_byte] | tick_mark
                    if self.peers_info[peer_id].bitfield == self.full_bitfield:
                        self.peers_with_whole_file += 1
                    if not bool(self.bitfield[piece_byte] & tick_mark) and piece_index not in self.current_requests:
                        uninterested_before = len(self.peers_info[peer_id].interesting_pieces) == 0
                        self.peers_info[peer_id].interesting_pieces.append(piece_index)
                        interested_now = len(self.peers_info[peer_id].interesting_pieces) != 0
                        if uninterested_before and interested_now:
                            self.send_message(peer_id, 2)
                case 5:
                    #Message is bitfield
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
                                self.peers_info[peer_id].interesting_pieces.append(((8*byte)+bit))
                    if interested:
                        self.send_message(peer_id, 2)
                        self.find_and_request(peer_id)
                    else:
                        self.send_message(peer_id, 3)
                        
                case 6:
                    #Message is request
                    if peer_id not in self.preferred_neighbors and peer_id != self.optimistically_unchoked_peer:
                        return
                    try:
                        piece_index = int.from_bytes(msg_data, byteorder="big")
                        piece_byte = piece_index // 8
                        piece_bit = piece_index % 8
                        tick_mark = 1 << (7 - piece_bit)
                        if not bool(self.bitfield[piece_byte] & tick_mark):
                            raise ValueError("Requested piece is not in this peer")
                        self.send_message(peer_id, 7, self.package_piece(piece_index)) 
                    except ValueError as e:
                        logging.info(f"Error: {e}")
                case 7:
                    #Message is piece
                    piece_index = int.from_bytes(msg_data[0:4], byteorder="big")
                    piece_byte = piece_index // 8
                    piece_bit = piece_index % 8
                    tick_mark = 1 << (7 - piece_bit)
                    if bool(self.bitfield[piece_byte] & tick_mark):
                        #Just going to ignore and return, this is a rare but possible case when the piece is requested, times out, rerequested, and then the original times out
                        #It doesn't actually cause an issue, so we'll just ignore, and next timeout will recognize it's there
                        return
                    piece_data = msg_data[4:]
                    with open(f"{self.subdir}/partial_piece_{piece_index}_{self.file_name}", "wb") as file_bytes:
                        file_bytes.write(piece_data)
                    self.pieces[piece_index] = True
                    self.num_pieces_held += 1
                    self.update_download_rate(peer_id, len(piece_data))
                    logging.info(f"Peer {self.id} has downloaded the piece {piece_index} from {peer_id}. Now the number of pieces it has is {self.num_pieces_held}")
                    self.bitfield[piece_byte] = self.bitfield[piece_byte] | tick_mark
                    self.check_for_completion()
                    piece_index_in_bytes = bytes((piece_index).to_bytes(4, byteorder="big"))
                    for peer in self.peers_info.values():
                        self.send_message(peer.peer_id, 4, piece_index_in_bytes)
                    if piece_index in self.current_requests:
                        self.current_requests.remove(piece_index)
                    self.remove_interest(piece_index)
                    if len(self.peers_info[peer_id].interesting_pieces) != 0:
                        self.find_and_request(peer_id)

                case _:
                    #Message is unexpected value
                    raise ValueError("Unexpected Message Type")
        except ValueError as e:
            logging.info(f"Error: {e}")

    def check_for_completion(self):
        if self.bitfield == self.full_bitfield:
            self.peers_with_whole_file += 1
            try:
                with open(f"{self.subdir}/{self.file_name}", "wb") as file_bytes:
                    for index in range(self.num_pieces):
                        if not self.pieces[index]:
                            raise RuntimeError("Peer should not be assembling file at current moment")
                        with open(f"{self.subdir}/partial_piece_{index}_{self.file_name}", "rb") as partial_p:
                            file_bytes.write(partial_p.read())
                        os.remove(f"{self.subdir}/partial_piece_{index}_{self.file_name}")
                logging.info(f"Peer {self.id} has downloaded the complete file.")
                self.has_file = True
            except RuntimeError as e:
                logging.info(f"Error: {e}")

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
            logging.info(f"Error: {e}")
        message = index_bytes + msg_data
        return message
    
    def find_and_request(self, peer_id):
        if len(self.peers_info[peer_id].interesting_pieces) == 0:
            return
        requested_piece = random.choice(self.peers_info[peer_id].interesting_pieces)
        new_timer = threading.Timer((self.unchoke_int*4), self.restore_interest, args=(requested_piece,))
        self.timers.append(new_timer)
        self.current_requests.append(requested_piece)
        self.remove_interest(requested_piece)
        new_timer.start()
        self.send_message(peer_id, 6, (requested_piece).to_bytes(4, byteorder="big"))

    def restore_interest(self, piece_index):
        piece_byte = piece_index // 8
        piece_bit = piece_index % 8
        tick_mark = 1 << (7 - piece_bit)
        if not bool(self.bitfield[piece_byte] & tick_mark):
            if piece_index in self.current_requests:
                self.current_requests.remove(piece_index)
            for neighbor in self.peers_info.values():
                if bool(neighbor.bitfield[piece_byte] & tick_mark):
                    neighbor.interesting_pieces.append(piece_index)
                    if len(neighbor.interesting_pieces) == 1:
                        self.send_message(neighbor.peer_id, 2)

    def remove_interest(self, piece_index):
        for neighbor in self.peers_info.values():
            if piece_index in neighbor.interesting_pieces:
                neighbor.interesting_pieces.remove(piece_index)
                if len(neighbor.interesting_pieces) == 0:
                    self.send_message(neighbor.peer_id, 3)
    
    # TODO: choking and unchoking
    def start_unchoke_timers(self):
        self.unchoke_timer = threading.Timer(self.unchoke_int, self.perform_unchoking)
        self.unchoke_timer.start()
        self.opt_unchoke_timer = threading.Timer(self.opt_unchoke_int, self.perform_optimistic_unchoking)
        self.opt_unchoke_timer.start()

    def perform_unchoking(self):
        if self.peers_with_whole_file == len(self.connections.keys())+1:
            return
        num_neighbors = min(self.numPrefNbors, len(self.peers_info.keys()))
        with self.unchoke_lock:
            if not self.has_file:
                filtered_download_rates = {k: v for k, v in self.download_rates.items() if k in self.neighbors_interested}
                sorted_peers = sorted(filtered_download_rates, key=filtered_download_rates.get, reverse=True)
                new_preferred_neighbors = set(sorted_peers[:num_neighbors])
                #Handling is there are less interested than amount for preferred
                if len(new_preferred_neighbors) < num_neighbors:
                    uninterested_download_rates = {k: v for k, v in self.download_rates.items() if k not in self.neighbors_interested}
                    extra_preferred_neighbors = set(random.sample(list(uninterested_download_rates.keys()), (num_neighbors - len(new_preferred_neighbors))))
                    new_preferred_neighbors = new_preferred_neighbors.union(extra_preferred_neighbors)
            else:
                new_preferred_neighbors = set(random.sample(list(self.peers_info.keys()), num_neighbors))
            if new_preferred_neighbors != self.preferred_neighbors:
                logging.info(f"Peer {self.id} has the preferred neighbors {','.join(map(str, sorted(new_preferred_neighbors)))}")
            for peer_id in new_preferred_neighbors - self.preferred_neighbors:
                self.send_message(peer_id, 1)  # Unchoke message
            for peer_id in self.preferred_neighbors - new_preferred_neighbors:
                self.send_message(peer_id, 0)  # Choke message
            self.preferred_neighbors = new_preferred_neighbors
            self.download_rates = {peer: 0 for peer in self.peers_info.keys()}
        self.unchoke_timer = threading.Timer(self.unchoke_int, self.perform_unchoking)
        self.unchoke_timer.start()

    def perform_optimistic_unchoking(self):
        if self.peers_with_whole_file < len(self.connections.keys())+1:
            return
        with self.unchoke_lock:
            choked_peers = ((set(self.neighbors_interested)).difference(self.preferred_neighbors))
            if  self.optimistically_unchoked_peer in choked_peers:
                choked_peers.remove(self.optimistically_unchoked_peer)
            if choked_peers:
                new_optimistically_unchoked_peer = random.choice(list(choked_peers))
                if new_optimistically_unchoked_peer != self.optimistically_unchoked_peer:
                    logging.info(f"Peer {self.id} has the optimistically unchoked neighbor {new_optimistically_unchoked_peer}")
                if self.optimistically_unchoked_peer:
                    self.send_message(self.optimistically_unchoked_peer, 0)  # Choke message
                self.send_message(new_optimistically_unchoked_peer, 1)  # Unchoke message
                self.optimistically_unchoked_peer = new_optimistically_unchoked_peer
        self.opt_unchoke_timer = threading.Timer(self.opt_unchoke_int, self.perform_optimistic_unchoking)
        self.opt_unchoke_timer.start()

    def update_download_rate(self, peer_id, bytes_downloaded):
        self.download_rates[peer_id] += bytes_downloaded
            

class PeerInfo():
    def __init__(self, peer_id, host_name, port_num, has_file):
        self.peer_id = int(peer_id)
        self.host_name = host_name
        self.port_num = int(port_num)
        self.has_file = has_file == '1'
        self.bitfield = None
        self.interesting_pieces = list()
        self.interested_in_me = False
        






def main():
    if len(sys.argv) < 2:
        raise SyntaxError("Need to provide a peer ID argument")
    id = int(sys.argv[1])
    host_name = None
    port = None
    has_file = None
    prev_peers = list()
    next_peers = list()

    # Get previous peers and this peer's port number
    with open('PeerInfo.cfg', 'r') as file:
        for line in file:
            words = line.split()
            if len(words) != 4:
                raise ValueError(f"Peer incorrectly identified for line {line}")
            # If the peer is found, set the host name, port, and has_file
            if int(words[0]) == id:
                # If the peer is found more than once, raise an error
                if port:
                    raise ValueError(f"Peer incorrectly appears multiple times")
                # Otherwise, set the host name, port, and has_file
                host_name = words[1]
                port = int(words[2])
                has_file = words[3] == '1'
            # If the port is not specified, add the peer to the list of previous peers
            elif not port:
                prev_peers.append(PeerInfo(*words))
            # If the port is specified, add the peer to the list of next peers
            else:
                next_peers.append(PeerInfo(*words))
    # If peer never found, throw error
    if not port:
        raise ValueError("Given Peer ID was not found in PeerInfo.cfg file")
    
    # Now Reading Common file and Setting values
    with open('Common.cfg', 'r') as file:
        # I'm going to get a little overcomplicated here, but I want to be prepared
        # for the case where the config file is given if a different order.
        for line in file:
            words = line.split()
            if len(words) == 0:
                #Allowing option of blank lines in between
                continue
            elif len(words) != 2:
                #Otherwise, wrong number of words is an error
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
        
    # Initialize PeerProcess
    peer = PeerProcess(id, host_name, port, has_file, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size, next_peers)
    
    # Set up connections to previous peers
    for prev_peer in prev_peers:
        peer.add_peer(prev_peer)
    
    peer.sockets_list = list(peer.connections.values())
    num_peers = len(peer.connections) + len(peer.next_peers) + 1 # Including itself, otherwise last one gets shut out
    print(num_peers)
    exponent = int(math.ceil(math.log2((peer.piece_size + 4 + 4 + 1)))) #For going to nearest power of 2 for buffer
    MAX_MSG_SIZE = 2**(exponent+2) #Giving extra space for buffer
    peer.start_unchoke_timers()
    peer.start_listening()
    peer.peer_buffers = {peer: bytearray() for peer in peer.peers_info.keys()}
    peer.peers_next_length = {peer: 0 for peer in peer.peers_info.keys()}
    while peer.peers_with_whole_file < num_peers:
        if len(peer.sockets_list) == 0:
            continue
        # Use select to check for readable sockets (those with incoming messages)
        read_sockets, _, _ = select.select(peer.sockets_list, [], [])
        
        for sock in read_sockets:
            # Receive the message from the socket
            buffer = sock.recv(MAX_MSG_SIZE)
            try:
                # Find the ID corresponding to the socket that sent the message
                peer_id = None
                for key, connection in peer.connections.items():
                    if connection == sock:
                        peer_id = key
                        break
                peer.peer_buffers[peer_id] += buffer
                #Read messages
                while len(peer.peer_buffers[peer_id]) > peer.peers_next_length[peer_id]:
                    if peer.peers_next_length[peer_id] == 0:
                        peer.peers_next_length[peer_id] = (int.from_bytes(peer.peer_buffers[peer_id][0:4], byteorder='big'))+4
                    if len(peer.peer_buffers[peer_id]) < peer.peers_next_length[peer_id]:
                        #Wait for more message to come in
                        break
                    else:
                        message = peer.peer_buffers[peer_id][0:peer.peers_next_length[peer_id]]
                        peer.peer_buffers[peer_id] = peer.peer_buffers[peer_id][peer.peers_next_length[peer_id]:]
                        peer.peers_next_length[peer_id] = 0
                        peer.read_message(peer_id, message)

            except RuntimeError as e:
                logging.info(f"Error: {e}")

    for conn in peer.connections.values():
        conn.close()
    peer.listening_socket.close()


if __name__ == "__main__":
    main()