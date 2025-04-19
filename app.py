import cv2
import streamlit as st
import numpy as np
import itertools
from PIL import Image
from io import BytesIO
from datetime import datetime
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

timestampcurrent = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"stego_image_{timestampcurrent}.png"

quant = np.array(
    [
        [16, 11, 10, 16, 24, 40, 51, 61],
        [12, 12, 14, 19, 26, 58, 60, 55],
        [14, 13, 16, 24, 40, 57, 69, 56],
        [14, 17, 22, 29, 51, 87, 80, 62],
        [18, 22, 37, 56, 68, 109, 103, 77],
        [24, 35, 55, 64, 81, 104, 113, 92],
        [49, 64, 78, 87, 103, 121, 120, 101],
        [72, 92, 95, 98, 112, 100, 103, 99],
    ]
)


# Fungsi Enkripsi/Dekripsi AES
def encrypt_message(message: str, password: str) -> bytes:
    if not password:
        raise ValueError("Password diperlukan untuk enkripsi")
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode("utf-8"))
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded_message = padder.update(message.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded_message) + encryptor.finalize()
    return salt + iv + encrypted


def decrypt_message(ciphertext: bytes, password: str) -> str:
    if len(ciphertext) < 32:
        return None
    salt = ciphertext[:16]
    iv = ciphertext[16:32]
    encrypted = ciphertext[32:]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    try:
        key = kdf.derive(password.encode("utf-8"))
    except:
        return None
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    try:
        decrypted_padded = decryptor.update(encrypted) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return decrypted.decode("utf-8")
    except:
        return None


class DCT:
    def __init__(self):
        self.message = None
        self.bitMess = None
        self.oriCol = 0
        self.oriRow = 0
        self.numBits = 0

    def encoding_image(self, img, secret_png, password):
        try:
            encrypted_bytes = encrypt_message(secret_png, password)
            encrypted_str = encrypted_bytes.decode("latin-1")
            self.message = f"{len(encrypted_str)}*{encrypted_str}"
            self.bitMess = self.toBits()

            row, col = img.shape[:2]
            self.oriRow, self.oriCol = row, col

            if (col // 8) * (row // 8) < len(encrypted_str) * 1.2:
                st.error(
                    "Error: Kapasitas gambar tidak mencukupi untuk pesan terenkripsi"
                )
                return None

            if row % 8 != 0 or col % 8 != 0:
                img = self.addPadd(img, row, col)

            row, col = img.shape[:2]
            bImg, gImg, rImg = cv2.split(img)
            bImg = np.float32(bImg)

            imgBlocks = [
                np.round(bImg[j : j + 8, i : i + 8] - 128)
                for (j, i) in itertools.product(range(0, row, 8), range(0, col, 8))
            ]

            dctBlocks = [cv2.dct(img_Block) for img_Block in imgBlocks]
            quantizedDCT = [dct_Block / quant for dct_Block in dctBlocks]

            messIndex = 0
            letterIndex = 0

            for quantizedBlock in quantizedDCT:
                DC = quantizedBlock[0][0]
                DC = np.uint8(DC)
                DC_bits = np.unpackbits(DC)
                DC_bits[7] = int(self.bitMess[messIndex][letterIndex])
                DC = np.packbits(DC_bits)
                quantizedBlock[0][0] = np.float32(DC) - 255

                letterIndex += 1
                if letterIndex == 8:
                    letterIndex = 0
                    messIndex += 1
                    if messIndex >= len(self.bitMess):
                        break

            sImgBlocks = [
                quantizedBlock * quant + 128 for quantizedBlock in quantizedDCT
            ]

            sImg = []
            for chunkRowBlocks in self.chunks(sImgBlocks, col // 8):
                for rowBlockNum in range(8):
                    for block in chunkRowBlocks:
                        sImg.extend(block[rowBlockNum])
            sImg = np.array(sImg).reshape(row, col)
            sImg = np.uint8(sImg)
            return cv2.merge((sImg, gImg, rImg))

        except Exception as e:
            st.error(f"Error encoding: {str(e)}")
            return None

    def decode_image(self, img, password):
        try:
            row, col = img.shape[:2]
            messageBits = []
            buff = 0
            messSize = None
            i = 0

            bImg, gImg, rImg = cv2.split(img)
            bImg = np.float32(bImg)

            imgBlocks = [
                bImg[j : j + 8, i : i + 8] - 128
                for (j, i) in itertools.product(range(0, row, 8), range(0, col, 8))
            ]

            quantizedDCT = [block / quant for block in imgBlocks]

            for block in quantizedDCT:
                DC = np.uint8(block[0][0])
                DC_bits = np.unpackbits(DC)
                lsb = DC_bits[7]

                buff |= (lsb ^ 1) << (7 - i)
                i += 1

                if i == 8:
                    messageBits.append(chr(buff))
                    buff = 0
                    i = 0

                    if not messSize and "*" in messageBits:
                        try:
                            delimiter_index = messageBits.index("*")
                            size_str = "".join(messageBits[:delimiter_index])
                            messSize = int(size_str)
                        except:
                            continue

                    if messSize and len(messageBits) >= delimiter_index + 1 + messSize:
                        encrypted_str = "".join(
                            messageBits[
                                delimiter_index + 1 : delimiter_index + 1 + messSize
                            ]
                        )
                        ciphertext = encrypted_str.encode("latin-1")
                        return decrypt_message(ciphertext, password)

            return ""

        except Exception as e:
            st.error(f"Error decoding: {str(e)}")
            return ""

    def chunks(self, l, n):
        for i in range(0, len(l), n):
            yield l[i : i + n]

    def addPadd(self, img, row, col):
        new_row = row + (8 - row % 8) if row % 8 != 0 else row
        new_col = col + (8 - col % 8) if col % 8 != 0 else col
        return cv2.resize(img, (new_col, new_row))

    def toBits(self):
        return [bin(ord(c))[2:].zfill(8) for c in self.message]


dct = DCT()

# UI Streamlit
st.title("🔐 Secure DCT Image Steganography")
tab1, tab2 = st.tabs(["🔒 Encode", "🔓 Decode"])

with tab1:
    st.header("Encode Message")
    img_file = st.file_uploader("Upload cover image", type=["png", "jpg", "jpeg"])
    secret_msg = st.text_area("Secret Message")
    encode_pass = st.text_input("Encryption Password", type="password")

    if st.button("Encode Message"):
        if img_file and secret_msg and encode_pass:
            img = Image.open(img_file).convert("RGB")
            img_array = np.array(img)

            encoded_img = dct.encoding_image(img_array, secret_msg, encode_pass)
            if encoded_img is not None:
                st.success("Encoding successful!")
                st.image(encoded_img, use_column_width=True)

                buf = BytesIO()
                Image.fromarray(encoded_img).save(buf, format="PNG")
                st.download_button(
                    "Download Stego Image", buf.getvalue(), filename, "image/png"
                )
        else:
            st.warning("Please fill all fields")

with tab2:
    st.header("Decode Message")
    stego_file = st.file_uploader("Upload stego image", type=["png", "jpg", "jpeg"])
    decode_pass = st.text_input("Decryption Password", type="password")

    if st.button("Decode Message"):
        if stego_file and decode_pass:
            try:
                img = Image.open(stego_file).convert("RGB")
                img_array = np.array(img)

                decoded_msg = dct.decode_image(img_array, decode_pass)
                st.success("Decoded Message:")
                st.code(decoded_msg)
            except Exception as e:
                st.error(f"Decoding error: {str(e)}")
        else:
            st.warning("Please provide both image and password")
