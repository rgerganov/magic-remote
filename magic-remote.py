#!/usr/bin/env python3
import sys
import argparse
import socket
try:
    from pynput import keyboard
except ImportError:
    HAVE_PYNPUT = False
    print("pynput not installed, keyboard input will not work")
else:
    HAVE_PYNPUT = True
from Cryptodome.Cipher import AES
from Cryptodome.Hash import SHA1

PORT = 40611
DEV_ID = "faeac9ec41c2f652"
DEV_DESCR = "Magic Remote"
DEBUG = False

def to_uint8(arr):
    tmp = [x if x >= 0 else x + 256 for x in arr]
    return bytes(tmp)

def get_cipher(pwd):
    pwd_bytes = pwd.encode('utf-8')
    suffix = [8, 56, -102, -124, 29, -75, -45, 74]
    to_hash = pwd_bytes + to_uint8(suffix)
    h = SHA1.new()
    h.update(to_hash)
    key = h.digest()[:16]
    iv = to_uint8([18, 111, -15, 33, 102, 71, -112, 109, -64, -23, 6, -103, -76, 99, -34, 101])
    # same as Cipher.getInstance("AES/CFB8/NoPadding") in Java
    return AES.new(key, AES.MODE_CFB, iv, segment_size=128)

def encrypt(pwd, data):
    cipher = get_cipher(pwd)
    return cipher.encrypt(data)

def decrypt(pwd, data):
    cipher = get_cipher(pwd)
    return cipher.decrypt(data)

def print_reply(code, data):
    cmd = data[6:38].decode('utf-8')
    body = data[6 + len(cmd):]
    try:
        body_decrypted = decrypt(code, body).decode('utf-8')
    except UnicodeDecodeError:
        print("Decryption failed, wrong pairing code?")
        sys.exit(1)
    if DEBUG:
        print("<< {} {}".format(cmd, body_decrypted))

def get_msg(cmd, body, code):
    prefix = bytearray(b'\x00\x00\x00\x01\x00\x00')
    body_bytes = body.encode('utf-8')
    if code is not None:
        body_bytes = encrypt(code, body_bytes)
    all = prefix + cmd.encode('utf-8') + body_bytes
    all[4] = len(all)
    return bytes(all)

def get_reqpair_msg():
    body = '{"dev_id":"%s","dev_descr":"%s"}' % (DEV_ID, DEV_DESCR)
    return get_msg('pairing-reqpairing-reqpairing-re', body, None)

def get_paircomplete_msg(code):
    cmd = 'pairing-complete-reqpairing-comp'
    body = '{"dev_id":"%s","dev_descr":"%s"}' % (DEV_ID, DEV_DESCR)
    return get_msg(cmd, body, code)

def pair(ip_addr):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip_addr, PORT))
        s.sendall(get_reqpair_msg())
        code = input("Enter pairing code displayed on TV: ")
        if len(code) != 6:
            print("Pairing code must be 6 digits")
            return
        s.sendall(get_paircomplete_msg(code))
        data = s.recv(4096)
        print_reply(code, data)

def get_req_connect_msg():
    body = '{"dev_id":"%s","dev_descr":"%s"}' % (DEV_ID, DEV_DESCR)
    return get_msg('connect-reqconnect-reqconnect-re', body, None)

def get_ping_msg(code):
    cmd = 'ping-reqping-reqping-reqping-req'
    body = '{"dev_id":"%s"}' % DEV_ID
    return get_msg(cmd, body, code)

def get_rccode_msg(code, rc_code):
    cmd = 'rc-code-reqrc-code-reqrc-code-re'
    body = '{"dev_id":"%s","dev_descr":"%s","rc_code":%d}' % (DEV_ID, DEV_DESCR, rc_code)
    return get_msg(cmd, body, code)

def send_rc_code(sock, code, rc_code):
    sock.sendall(get_rccode_msg(code, rc_code))
    sock.sendall(get_ping_msg(code))
    data = sock.recv(4096)
    print_reply(code, data)

def send_key(ip_addr, code, rc_code):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip_addr, PORT))
        s.sendall(get_req_connect_msg())
        data = s.recv(4096)
        print_reply(code, data)
        s.sendall(get_ping_msg(code))
        data = s.recv(4096)
        print_reply(code, data)
        send_rc_code(s, code, rc_code)

def get_char_msg(code, key_code, meta):
    cmd = 'msg-rc-kb-key-reqmsg-rc-kb-keyms'
    # don't care about unicode, just use key_code as ucode
    body = '{"dev_id":"%s","dev_descr":"%s","kb_key_code":%d,"meta":%d,"ucode":%d}' % (DEV_ID, DEV_DESCR, key_code, meta, key_code)
    return get_msg(cmd, body, code)

def send_text(ip_addr, code, text):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip_addr, PORT))
        s.sendall(get_req_connect_msg())
        data = s.recv(4096)
        for c in text:
            s.sendall(get_char_msg(code, ord(c), 0))

def on_press(sock, code, key):
    if isinstance(key, keyboard.KeyCode):
        if key.char == '+':
            # volume up
            send_rc_code(sock, code, 146)
        elif key.char == '-':
            # volume down
            send_rc_code(sock, code, 147)
        elif key.char == 'i':
            # info button
            send_rc_code(sock, code, 157)
        elif key.char >= '0' and key.char <= '9':
            # number keys
            send_rc_code(sock, code, 128 + ord(key.char) - ord('0'))
        elif key.char == 'm':
            # mute
            send_rc_code(sock, code, 176)
        elif key.char == 'b':
            # rewind
            send_rc_code(sock, code, 150)
        elif key.char == 'f':
            # fast forward
            send_rc_code(sock, code, 144)
        elif key.char == 'p':
            # play/pause
            send_rc_code(sock, code, 139)
        elif key.char == 't':
            # tv button
            send_rc_code(sock, code, 138)
        elif key.char == 'o':
            # power button
            send_rc_code(sock, code, 140)
    elif key == keyboard.Key.esc:
        # home button
        send_rc_code(sock, code, 141)
    elif key == keyboard.Key.backspace:
        # back button
        send_rc_code(sock, code, 143)
    elif key == keyboard.Key.enter:
        # ok button
        send_rc_code(sock, code, 172)
    elif key == keyboard.Key.up:
        send_rc_code(sock, code, 189)
    elif key == keyboard.Key.down:
        send_rc_code(sock, code, 190)
    elif key == keyboard.Key.left:
        send_rc_code(sock, code, 191)
    elif key == keyboard.Key.right:
        send_rc_code(sock, code, 171)
    elif key == keyboard.Key.page_up:
        # channel up
        send_rc_code(sock, code, 188)
    elif key == keyboard.Key.page_down:
        # channel down
        send_rc_code(sock, code, 145)
    elif key == keyboard.Key.f1:
        # red button (F1)
        send_rc_code(sock, code, 178)
    elif key == keyboard.Key.f2:
        # green button (F2)
        send_rc_code(sock, code, 177)
    elif key == keyboard.Key.f3:
        # yellow button (F3)
        send_rc_code(sock, code, 185)
    elif key == keyboard.Key.f4:
        # blue button (F4)
        send_rc_code(sock, code, 186)

def read_kbd(ip_addr, code):
    print("Sending keyboard input to STB, Ctrl+C to exit")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip_addr, PORT))
        s.sendall(get_req_connect_msg())
        data = s.recv(4096)
        print_reply(code, data)
        s.sendall(get_ping_msg(code))
        data = s.recv(4096)
        print_reply(code, data)
        on_press_fn = lambda key : on_press(s, code, key)
        with keyboard.Listener(on_press=on_press_fn) as listener:
            listener.join()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MAG Remote Control')
    parser.set_defaults(action='none')
    subparsers = parser.add_subparsers()
    pair_parser = subparsers.add_parser('pair', help='pair with STB')
    pair_parser.set_defaults(action='pair')
    pair_parser.add_argument('ip', type=str, help='STB IP address')
    if HAVE_PYNPUT:
        input_parser = subparsers.add_parser('input', help='send input from kbd')
        input_parser.add_argument('ip', type=str, help='STB IP address')
        input_parser.add_argument('code', type=str, help='pairing code')
        input_parser.set_defaults(action='input')
    send_key_parser = subparsers.add_parser('send-key', help='send single key')
    send_key_parser.add_argument('ip', type=str, help='STB IP address')
    send_key_parser.add_argument('code', type=str, help='pairing code')
    send_key_parser.add_argument('rc_code', type=int, help='rc code')
    send_key_parser.set_defaults(action='send-key')
    send_text_parser = subparsers.add_parser('send-text', help='send text')
    send_text_parser.add_argument('ip', type=str, help='STB IP address')
    send_text_parser.add_argument('code', type=str, help='pairing code')
    send_text_parser.add_argument('text', type=str, help='text to send')
    send_text_parser.set_defaults(action='send-text')

    args = parser.parse_args()
    if hasattr(args, 'code') and len(args.code) != 6:
        print("Pairing code must be 6 digits")
        sys.exit(1)
    if args.action == 'pair':
        pair(args.ip)
    elif args.action == 'input':
        read_kbd(args.ip, args.code)
    elif args.action == 'send-key':
        send_key(args.ip, args.code, args.rc_code)
    elif args.action == 'send-text':
        send_text(args.ip, args.code, args.text)
    else:
        parser.print_help()
