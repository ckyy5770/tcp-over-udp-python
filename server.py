import socket
import time
import utils
from utils import States
from utils import Protocols

PROTOCOL = Protocols.STOP_AND_WAIT

UDP_IP = "127.0.0.1"
UDP_PORT = 5005

# some global states
my_next_seq = -1
client_next_seq = -1
client_addr = None

# initial server_state
server_state = States.CLOSED

sock = socket.socket(socket.AF_INET,    # Internet
                     socket.SOCK_DGRAM) # UDP

sock.bind((UDP_IP, UDP_PORT)) # wait for connection

# Some helper functions to keep the code clean and tidy
def update_server_state(new_state):
  global server_state
  if utils.DEBUG:
    print(server_state, '->', new_state)
  server_state = new_state

# Receive a message and return header, body and addr
# addr is used to reply to the client
# this call is blocking
def recv_msg():
  data, addr = sock.recvfrom(1024)
  header = utils.bits_to_header(data)
  body = utils.get_body_from_data(data)
  return (header, body, addr)

# the server runs in an infinite loop and takes
# action based on current state and updates its state
# accordingly
# You will need to add more states, please update the possible
# states in utils.py file
while True:
  if server_state == States.CLOSED:
    # we already started listening, just update the state
    update_server_state(States.LISTEN)
  elif server_state == States.LISTEN:
    # we are waiting for a message
    header, body, addr = recv_msg()
    # if received message is a syn message, it's a connection
    # initiation
    if header.syn == 1:
      # update seq numbers
      my_next_seq = utils.rand_int() # we randomly pick a sequence number
      client_next_seq = header.seq_num + 1
      # update client addr
      client_addr = addr

      # make a syn-ack header and send to to client
      syn_ack_header = utils.Header(my_next_seq, client_next_seq, syn=1, ack=1, fin=0)
      sock.sendto(syn_ack_header.bits(), client_addr)
      # update my seq number
      my_next_seq += 1
      # update server state
      update_server_state(States.SYN_RECEIVED)
    else:
      # discard non-SYN messages
      pass

  elif server_state == States.SYN_RECEIVED:
    # we are waiting for a message
    header, body, addr = recv_msg()
    # we only receive message from our client addr
    # and we only expect a ACK message
    if addr == client_addr and header.ack == 1:
        # check if seq numbers are synchronized
        if my_next_seq == header.ack_num and client_next_seq == header.seq_num:
            # connection established on the server's perspective
            # update client next seq and server state
            client_next_seq += 1
            update_server_state(States.ESTABLISHED)
        else:
            # client server seq number doesn't match, close connection
            my_next_seq = -1
            client_next_seq = -1
            client_addr = None
            update_server_state(States.CLOSED)
    else:
        # unexpected messages
        pass

  elif server_state == States.ESTABLISHED:
      # we are waiting for a message
      header, body, addr = recv_msg()
      if addr == client_addr and header.fin == 1:
          # client initiate a termination
          # update client seq
          client_next_seq = header.seq_num + 1
          # send ack message
          ack_header = utils.Header(my_next_seq, client_next_seq, syn=0, ack=1, fin=0)
          sock.sendto(ack_header.bits(), client_addr)
          # update my seq number
          my_next_seq += 1
          # update server state
          update_server_state(States.CLOSE_WAIT)
      elif addr == client_addr:
          # stop and wait protocol
          if PROTOCOL == Protocols.STOP_AND_WAIT:
              # received a non-termination message from client
              # if the seq number is the number we expected, receive the message and ack it
              if header.seq_num == client_next_seq:
                  # print the received message in
                  print(body)
                  # update client next seq
                  client_next_seq += 1
                  # send ack message
                  ack_header = utils.Header(my_next_seq, client_next_seq, syn=0, ack=1, fin=0)
                  sock.sendto(ack_header.bits(), client_addr)
                  # update my seq number
                  my_next_seq += 1
      else:
          # unexpected messages
          pass

  elif  server_state == States.CLOSE_WAIT:
      # wait for application to be ready to end
      # in this test case, we just wait for 1 seconds
      time.sleep(1)
      # now that app running on the server side is ready to close
      # we send a FIN to client
      fin_header = utils.Header(my_next_seq, 0, syn=0, ack=0, fin=1)
      sock.sendto(fin_header.bits(), client_addr)
      # update my seq number
      my_next_seq += 1
      # update server state
      update_server_state(States.LAST_ACK)

  elif  server_state == States.LAST_ACK:
      # we are waiting for a ack message
      header, body, addr = recv_msg()
      if addr == client_addr and header.ack == 1:
          # received client 's final ack
          # clear server state
          my_next_seq = -1
          client_next_seq = -1
          client_addr = None
          update_server_state(States.CLOSED)
      else:
          # unexpected messages
          pass
  else:
    raise RuntimeError("invalid server states")

