import streamlit as st
import cv2
import numpy as np
from datetime import datetime
from io import BytesIO
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import os

timestampcurrent = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"stego_image_{timestampcurrent}.png"

def encrypt_message(message: str, password: str) -> bytes:
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode())
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(message.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return salt + iv + ciphertext


def decrypt_message(ciphertext: bytes, password: str) -> str:
    try:
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
        key = kdf.derive(password.encode())
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(encrypted) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return decrypted.decode()
    except:
        return None


def main():
    st.title("🔒 OccultaPix Secure DCT Steganography")
    tab1, tab2 = st.tabs(["Encode", "Decode"])

    with tab1:
        st.header("Encode Pesan")
        img_file = st.file_uploader("Upload gambar cover", type=["jpg", "png", "jpeg"])
        secret_msg = st.text_area("Pesan rahasia")
        password = st.text_input("Password", type="password")

        if img_file and secret_msg and password:
            if st.button("Encode"):
                try:
                    # Baca dan proses gambar
                    file_bytes = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

                    # Enkripsi pesan
                    encrypted = encrypt_message(secret_msg, password)
                    encrypted_str = f"{len(encrypted)}*{encrypted.decode('latin-1')}"
                    binary_msg = "".join([format(ord(c), "08b") for c in encrypted_str])

                    # Konversi ke YCrCb
                    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
                    rows, cols = ycrcb.shape[:2]
                    rows = rows - (rows % 8)
                    cols = cols - (cols % 8)
                    ycrcb = ycrcb[:rows, :cols]

                    # Validasi kapasitas
                    max_bits = (rows // 8) * (cols // 8)
                    if len(binary_msg) > max_bits:
                        st.error("Gambar terlalu kecil untuk pesan ini!")
                        return

                    # Embedding
                    y_channel = ycrcb[:, :, 0].astype(np.float32)
                    msg_idx = 0
                    SCALE = 50

                    for row in range(0, rows, 8):
                        for col in range(0, cols, 8):
                            if msg_idx >= len(binary_msg):
                                break
                            block = y_channel[row : row + 8, col : col + 8]
                            dct_block = cv2.dct(block)
                            if msg_idx < len(binary_msg):
                                bit = int(binary_msg[msg_idx])
                                dct_block[5, 5] = bit * SCALE + 1
                                msg_idx += 1
                            modified = cv2.idct(dct_block)
                            y_channel[row : row + 8, col : col + 8] = modified

                    # Konversi kembali ke uint8
                    ycrcb[:, :, 0] = np.clip(y_channel, 0, 255).astype(np.uint8)
                    result = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

                    # Konversi ke bytes
                    is_success, buffer = cv2.imencode(".png", result)

                    if is_success:
                        # Tampilkan preview
                        st.image(
                            cv2.cvtColor(result, cv2.COLOR_BGR2RGB),
                            caption="Gambar dengan pesan tersembunyi",
                            use_column_width=True,
                        )

                        # Download button
                        io_buf = BytesIO(buffer)
                        st.download_button(
                            "Download Gambar Stego",
                            io_buf.getvalue(),
                            filename,
                            "image/png",
                        )
                    else:
                        st.error("Gagal menyimpan gambar hasil encoding")

                except Exception as e:
                    st.error(f"Error: {str(e)}")

    with tab2:
        st.header("Decode Pesan")
        stego_file = st.file_uploader(
            "Upload gambar stego", type=["png", "jpg", "jpeg"]
        )
        password = st.text_input("Password", type="password", key="decode")

        if stego_file and password:
            if st.button("Decode"):
                try:
                    # Baca gambar
                    file_bytes = np.asarray(
                        bytearray(stego_file.read()), dtype=np.uint8
                    )
                    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

                    # Ekstraksi pesan
                    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
                    rows, cols = ycrcb.shape[:2]
                    rows = rows - (rows % 8)
                    cols = cols - (cols % 8)
                    ycrcb = ycrcb[:rows, :cols]

                    y_channel = ycrcb[:, :, 0].astype(np.float32)
                    extracted_bits = []
                    THRESHOLD = 25

                    for row in range(0, rows, 8):
                        for col in range(0, cols, 8):
                            block = y_channel[row : row + 8, col : col + 8]
                            dct_block = cv2.dct(block)
                            bit = 1 if dct_block[5, 5] > THRESHOLD else 0
                            extracted_bits.append(str(bit))

                    # Konversi ke string
                    bit_str = "".join(extracted_bits)
                    bytes_list = [bit_str[i : i + 8] for i in range(0, len(bit_str), 8)]
                    encrypted_str = "".join([chr(int(byte, 2)) for byte in bytes_list])

                    # Split length dan ciphertext
                    delimiter = encrypted_str.find("*")
                    if delimiter == -1:
                        st.error("Pesan tidak valid!")
                        return

                    cipher_len = int(encrypted_str[:delimiter])
                    ciphertext = encrypted_str[
                        delimiter + 1 : delimiter + 1 + cipher_len
                    ]

                    # Dekripsi
                    decrypted = decrypt_message(ciphertext.encode("latin-1"), password)
                    st.success("Pesan yang diekstrak:")
                    st.code(decrypted)

                except Exception as e:
                    st.error(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
