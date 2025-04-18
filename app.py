import cv2
import streamlit as st
import numpy as np
import itertools
from PIL import Image
from io import BytesIO

def message2binary(message):
    if type(message) == str:
        result = "".join([format(ord(i), "08b") for i in message])
    elif type(message) == bytes or type(message) == np.ndarray:
        result = [format(i, "08b") for i in message]
    elif type(message) == int or type(message) == np.uint8:
        result = format(message, "08b")
    else:
        raise TypeError("Input type is not supported")

    return result


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


class DCT:
    def __init__(self):
        self.message = None
        self.bitMess = None
        self.oriCol = 0
        self.oriRow = 0
        self.numBits = 0

    def encoding_image(self, img, secret_png):
        secret = secret_png
        self.message = str(len(secret)) + "*" + secret
        self.bitMess = self.toBits()

        row, col = img.shape[:2]
        self.oriRow, self.oriCol = row, col

        if (col / 8) * (row / 8) < len(secret):
            print("Error: Message too large to encode in image")
            return

        if row % 8 != 0 or col % 8 != 0:
            img = self.addPadd(img, row, col)

        row, col = img.shape[:2]

        # split image into RGB channels
        bImg, gImg, rImg = cv2.split(img)

        # message to be hid in blue channel so converted to type float32 for dct function
        bImg = np.float32(bImg)
        # print(bImg[0:8,0:8])

        # break into 8x8 blocks
        imgBlocks = [
            np.round(bImg[j : j + 8, i : i + 8] - 128)
            for (j, i) in itertools.product(range(0, row, 8), range(0, col, 8))
        ]

        dctBlocks = [np.round(cv2.dct(img_Block)) for img_Block in imgBlocks]

        # blocks then run through quantization table
        quantizedDCT = [np.round(dct_Block / quant) for dct_Block in dctBlocks]

        # set LSB in DC value corresponding bit of message
        messIndex = 0
        letterIndex = 0

        for quantizedBlock in quantizedDCT:
            # find LSB in DC coeff and replace with message bit
            DC = quantizedBlock[0][0]
            DC = np.uint8(DC)
            DC = np.unpackbits(DC)
            # print(DC, end=' ')
            DC[7] = self.bitMess[messIndex][letterIndex]
            # print(DC,end= ' ')
            DC = np.packbits(DC)

            # print(DC)
            DC = np.float32(DC)
            DC = DC - 255
            quantizedBlock[0][0] = DC

            letterIndex = letterIndex + 1
            if letterIndex == 8:
                letterIndex = 0
                messIndex = messIndex + 1
                if messIndex == len(self.message):
                    break

        # print(quantizedDCT[1][0])

        # blocks run inversely through quantization table
        sImgBlocks = [quantizedBlock * quant + 128 for quantizedBlock in quantizedDCT]

        # blocks run through inverse DCT
        # sImgBlocks = [cv2.idct(B)+128 for B in quantizedDCT]

        # puts the new image back together
        sImg = []
        for chunkRowBlocks in self.chunks(sImgBlocks, col / 8):
            for rowBlockNum in range(8):
                for block in chunkRowBlocks:
                    sImg.extend(block[rowBlockNum])
        sImg = np.array(sImg).reshape(row, col)

        # converted from type float32
        sImg = np.uint8(sImg)

        sImg = cv2.merge((sImg, gImg, rImg))
        # cv2.imwrite(outIm, sImg)
        return sImg

    def decode_image(self, img):
        row, col = img.shape[:2]

        messSize = None
        messageBits = []
        buff = 0

        # split image into RGB channels
        bImg, gImg, rImg = cv2.split(img)
        # print(bImg[0:8,0:8])
        # message hid in blue channel so converted to type float32 for dct function
        bImg = np.float32(bImg)
        # print(bImg[0:8,0:8])

        # break into 8x8 blocks
        imgBlocks = [
            bImg[j : j + 8, i : i + 8] - 128
            for (j, i) in itertools.product(range(0, row, 8), range(0, col, 8))
        ]
        # blocks run through quantization table
        # quantizedDCT = [dct_Block/ (quant) for dct_Block in dctBlocks]
        quantizedDCT = [img_Block / quant for img_Block in imgBlocks]
        # print(quantizedDCT[1][0])
        i = 0
        # message extracted from LSB of DC coeff
        for quantizedBlock in quantizedDCT:
            DC = quantizedBlock[0][0]
            DC = np.uint8(DC)
            DC = np.unpackbits(DC)
            if DC[7] == 1:
                buff += (0 & 1) << (7 - i)
            elif DC[7] == 0:
                buff += (1 & 1) << (7 - i)
            i = 1 + i
            if i == 8:

                messageBits.append(chr(buff))
                buff = 0
                i = 0

                if messageBits[-1] == "*" and messSize is None:
                    try:
                        messSize = int("".join(messageBits[:-1]))
                    except:
                        pass
            if len(messageBits) - len(str(messSize)) - 1 == messSize:
                return "".join(messageBits)[len(str(messSize)) + 1 :]

        # return ""
        sImgBlocks = [quantizedBlock * quant + 128 for quantizedBlock in quantizedDCT]
        sImg = []
        for chunkRowBlocks in self.chunks(sImgBlocks, col / 8):
            for rowBlockNum in range(8):
                for block in chunkRowBlocks:
                    sImg.extend(block[rowBlockNum])
        sImg = np.array(sImg).reshape(row, col)
        sImg = np.uint8(sImg)
        sImg = cv2.merge((sImg, gImg, rImg))

        return ""

    def chunks(self, l, n):
        m = int(n)
        for i in range(0, len(l), m):
            yield l[i : i + m]

    def addPadd(self, img, row, col):
        img = cv2.resize(img, (col + (8 - col % 8), row + (8 - row % 8)))
        return img

    def toBits(self):
        bits = []

        for char in self.message:
            binval = bin(ord(char))[2:].rjust(8, "0")

            # for bit in binval:
            bits.append(binval)

        self.numBits = bin(len(bits))[2:].rjust(8, "0")
        return bits


dct = DCT()

# UI Streamlit
st.title("🕵️‍♂️ DCT Image Steganography")

tab1, tab2 = st.tabs(["📥 Embed Message", "📤 Extract Message"])

with tab1:
    st.header("Sisipkan Pesan ke Gambar")
    uploaded_image = st.file_uploader(
        "Upload Gambar", type=["png", "jpg", "jpeg"], key="embed"
    )
    message = st.text_input("Masukkan Pesan yang Ingin Disisipkan")

    if st.button("🔐 Sisipkan Pesan"):
        if uploaded_image and message:
            print(uploaded_image)
            image = Image.open(uploaded_image).convert("RGB")
            img_array = np.array(image)

            encoded_img = dct.encoding_image(img_array, message)

            if encoded_img is not None:
                st.success("Pesan berhasil disisipkan!")
                st.image(
                    encoded_img, caption="Gambar dengan pesan", use_column_width=True
                )

                buffered = BytesIO()
                result_image = Image.fromarray(encoded_img)
                result_image.save(
                    buffered, format="PNG"
                )  # Simpan sebagai PNG ke buffer

                st.download_button(
                    "⬇️ Unduh Gambar",
                    data=buffered.getvalue(),  # Ambil byte dari buffer
                    file_name="stego_image.png",
                    mime="image/png",
                )
            else:
                st.error("Gagal menyisipkan pesan. Gambar terlalu kecil?")
        else:
            st.warning("Harap unggah gambar dan masukkan pesan.")

with tab2:
    st.header("Ekstrak Pesan dari Gambar")
    uploaded_encoded = st.file_uploader(
        "Upload Gambar yang Disisipi", type=["png", "jpg", "jpeg"], key="extract"
    )

    if st.button("📤 Ekstrak Pesan"):
        if uploaded_encoded is not None:
            try:
                image = Image.open(uploaded_encoded)
                image.verify()  # Verifikasi integritas gambar
                uploaded_encoded.seek(0)  # Reset pointer

                image = Image.open(uploaded_encoded).convert("RGB")
                img_array = np.array(image)

                extracted_message = dct.decode_image(img_array)
                print("ini print", extracted_message)
                if extracted_message:
                    st.success("Pesan berhasil diambil!")
                    st.code(extracted_message)
                else:
                    st.warning("Tidak ditemukan pesan dalam gambar.")
            except Exception as e:
                st.error(f"Gagal memproses gambar: {e}")
        else:
            st.warning("Harap unggah gambar.")
