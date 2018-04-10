from multiprocessing import Value
from threading import Timer
from threading import Thread
from utils import States
from utils import Protocols
import multiprocessing
import random
import socket
import time
import utils

PROTOCOL = Protocols.STOP_AND_WAIT

UDP_IP = "127.0.0.1"
UDP_PORT = 5005
MSS = 12 # maximum segment size
MSL = 120 # maximum segment lifetime - 120 sec

sock = socket.socket(socket.AF_INET,    # Internet
                     socket.SOCK_DGRAM) # UDP

def send_udp(message):
  sock.sendto(message, (UDP_IP, UDP_PORT))

class Client:
  def __init__(self):
    self.client_state = States.CLOSED
    self.my_next_seq = -1
    self.server_next_seq = -1
    self.last_received_ack = -1
    self.handshake()

  def handshake(self):
    if self.client_state == States.CLOSED:
      seq_num = utils.rand_int()
      syn_header = utils.Header(seq_num, 0, syn = 1, ack = 0, fin=0)
      # for this case we send only header;
      # if you need to send data you will need to append it
      send_udp(syn_header.bits())
      # update client seq number
      self.my_next_seq = seq_num + 1
      self.update_state(States.SYN_SENT)
    else:
      raise  RuntimeError("invalid states for start a handshake.")

    # we wait for server to send back a SYN-ACK message
    if self.client_state == States.SYN_SENT:
      recv_data, addr = sock.recvfrom(1024)
      header = utils.bits_to_header(recv_data)
      # server syn header should have both syn and ack fields
      # and the ack_num should be client next sequence number
      if header.ack == 1 and header.syn == 1 and header.ack_num == self.my_next_seq:
        self.server_next_seq = header.seq_num + 1
        self.last_received_ack = header.ack_num + 1
      else:
        raise RuntimeError("invalid server SYN-reply, handshake failed.")

      # we send back ACK message
      ack_header = utils.Header(self.my_next_seq, self.server_next_seq, syn = 0, ack = 1, fin=0)
      send_udp(ack_header.bits())
      # update my seq
      self.my_next_seq += 1
      # update state -> connection established on the client's perspective
      self.update_state(States.ESTABLISHED)
    else:
      raise RuntimeError("invalid states for waiting server SYN-reply.")

  def terminate(self):
    if self.client_state == States.ESTABLISHED:
      # send FIN message
      fin_header = utils.Header(self.my_next_seq, 0, syn=0, ack=0, fin=1)
      send_udp(fin_header.bits())
      # update my seq
      self.my_next_seq += 1
      # update state
      self.update_state(States.FIN_WAIT_1)
    else:
      raise RuntimeError("invalid states for termination")

    # wait for ack
    if self.client_state == States.FIN_WAIT_1:
      recv_data, addr = sock.recvfrom(1024)
      header = utils.bits_to_header(recv_data)
      if header.ack == 1 and header.ack_num == self.my_next_seq:
        # update server seq
        self.server_next_seq = header.seq_num + 1
        # update client state
        self.update_state(States.FIN_WAIT_2)
      else:
        raise RuntimeError("invalid server ack")
    else:
      raise RuntimeError("invalid states for termination")

    # wait for server FIN and send back a ACK
    if self.client_state == States.FIN_WAIT_2:
      recv_data, addr = sock.recvfrom(1024)
      header = utils.bits_to_header(recv_data)
      if header.fin == 1:
        # update server seq
        self.server_next_seq = header.seq_num + 1
        # send back a ack
        ack_header = utils.Header(self.my_next_seq, self.server_next_seq, syn=0, ack=1, fin=0)
        send_udp(ack_header.bits())
        # update client seq
        self.my_next_seq += 1
        # update client state
        self.update_state(States.TIME_WAIT)
      else:
        raise RuntimeError("invalid server fin")
    else:
      raise RuntimeError("invalid states for termination")

    # wait for 2 maximum segment life time then close the client
    if self.client_state == States.TIME_WAIT:
      time.sleep(2 * MSL)

      self.my_next_seq = -1
      self.server_next_seq = -1
      self.update_state(States.CLOSED)
    else:
      raise RuntimeError("invalid states for termination")


  def update_state(self, new_state):
    if utils.DEBUG:
      print(self.client_state, '->', new_state)
    self.client_state = new_state

  def send_reliable_message(self, message):
    # divide the message into pieces according to MSS
    messages = [message[i:i+MSS] for i in range(0, len(message), MSS)]
    # send messages
    # we loop/wait until we receive all ack.
    if PROTOCOL == Protocols.STOP_AND_WAIT:
      current_seg = 0
      while True:
        lra = self.last_received_ack
        # send one message and expect one ack
        header = utils.Header(self.my_next_seq, 0, syn = 0, ack = 0, fin=0)
        seg = header.bits() + messages[current_seg].encode()
        send_udp(seg)
        # receive ack for one second
        self.receive_acks()
        # received ack, update states, else, just resend the message in the next loop
        if lra != self.last_received_ack:
          self.my_next_seq += 1
          current_seg += 1
        # check if this is the last seg
        print(self.client_state)
        if current_seg >= len(messages):
          break
    else:
      raise RuntimeError("invalid transmission protocol")


  # received one ack for stop and wait protocol
  def receive_acks_sub_process_stop_and_wait(self, lst_rec_ack_shared):
    print("here")
    while True:
      print("here2")
      recv_data, addr = sock.recvfrom(1024)
      header = utils.bits_to_header(recv_data)
      print(header.ack_num)
      print("vs")
      print(lst_rec_ack_shared.value)
      if header.ack == 1 and header.ack_num == lst_rec_ack_shared.value + 1:
        lst_rec_ack_shared.value = header.ack_num
        break


  # these two methods/function can be used receive messages from
  # server. the reason we need such mechanism is `recv` blocking
  # and we may never recieve a package from a server for multiple
  # reasons.
  # 1. our message is not delivered so server cannot send an ack.
  # 2. server responded with ack but it's not delivered due to
  # a network failure.
  # these functions provide a mechanism to receive messages for
  # 1 second, then the client can decide what to do, like retransmit
  # if not all packets are acked.
  # you are free to implement any mechanism you feel comfortable
  # especially, if you have a better idea ;)
  def receive_acks_sub_process(self, lst_rec_ack_shared):
    while True:
      recv_data, addr = sock.recvfrom(1024)
      header = utils.bits_to_header(recv_data)
      if header.ack_num > lst_rec_ack_shared.value:
        lst_rec_ack_shared.value = header.ack_num

  def receive_acks(self):
    # Start receive_acks_sub_process as a process
    lst_rec_ack_shared = Value('i', self.last_received_ack)
    #p=0
    #if PROTOCOL == Protocols.STOP_AND_WAIT:
    p = multiprocessing.Process(target=self.receive_acks_sub_process_stop_and_wait, args=(self, lst_rec_ack_shared,))
      #p = multiprocessing.Process(target=self.receive_acks_sub_process, args=(lst_rec_ack_shared,))
    p.start()
    print("hello")
    # Wait for 1 seconds or until process finishes
    p.join(10)
    # If process is still active, we kill it
    if p.is_alive():
      print("hello3")
      p.terminate()
      p.join()
    print("hello2")
    # here you can update your client's instance variables.
    self.last_received_ack = lst_rec_ack_shared.value

# we create a client, which establishes a connection
client = Client()
# we send a message
client.send_reliable_message("This message is to be received in pieces")
# we terminate the connection
#client.terminate()
