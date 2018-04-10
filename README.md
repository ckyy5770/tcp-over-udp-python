# tcp-over-udp-python

## Milestone 1 modifications

Client:

init: add new initial value for server_next_seq and my_next_seq

handshake: complete handshake process

terminate: complete termination process

UTILS:

states: add ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, TIME_WAIT, CLOSE_WAIT, LAST_ACK, CLOSED state

header: add FIN

SERVER:

add global states: my_next_seq, client_next_seq

complete code within the infinite loop

## Milestone 2 Modifications

Add three protocol Enums -> STOP_AND_WAIT, GO_BACK_N, SLIDING_WINDOW

To test a specific protocol, please modify the global variable PROTOCOL located on the very first line of client.py and server.py.