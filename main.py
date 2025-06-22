import ColorPrint as cprint
import pymupdf
from ebooklib import epub
import os
import hashlib

# os.makedirs("test_images", exist_ok=True)
os.makedirs("test_output/test_images", exist_ok=True)
HEADER_FOOTER_THRESHOLD = 70 # threshold for the text extraction. may need to change for every document
IGNORE_IMAGE_THRESHOLD = 0.7 # only extract images in this top % of the page. for example 0.7 ignores the bottom 30% (0.3) of the page

# TODO use first image as cover
def create_epub():
    pass

# TODO use TOC to split chapters
def split_to_chapters(doc, extracted_content):
    full_text, images = extracted_content
    print(doc.get_toc)
    pass

def extract_text_from_lines(lines):
    text = ""
    for line in lines:
        line_text = ""
        for span in line["spans"]:
            span_font = span["font"].lower()
            if "italic" in span_font:
                line_text += f"<i>{span["text"]}</i>"
            elif "bold" in span_font:
                line_text += f"<b>{span["text"]}</b>"
            else: 
                line_text += span["text"]
        text += f"<p>{line_text}</p>"
    return text

def extract_img_from_xref(doc, xref):
    pix = pymupdf.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3: # CMYK: convert to RGB first
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix

def extract_pdf(doc: pymupdf.Document,start=0, end=-1):
    end = doc.page_count if end == -1 else end
    content = ""
    images = {} # key: filename, value: image data
    ignored_images = {}

    for i in range(start, end):
        cprint.blue(f"-----PAGE {i+1}------")
        page = doc[i]
        page_height = page.rect.height
        dicts = page.get_text("dict", sort=True)
        img_count = 0
        img_list = page.get_images()
        get_images_count = len(img_list)

        for element in dicts["blocks"]:
            if element["type"] == 0: # text block
                # ignore text blocks in headers and footers
                if element["bbox"][1] <= HEADER_FOOTER_THRESHOLD or element["bbox"][1] >= page_height - HEADER_FOOTER_THRESHOLD:
                    continue
                text = extract_text_from_lines(element["lines"])
                content += text
            
            elif element["type"] == 1: # image
                img_count += 1
                img_data = element["image"]
                img_bbox = element["bbox"]
                # img_height =  img_bbox[3] - img_bbox[1]
                img_filename = f"page_{i+1}-image_{img_count}.png"
                ignored = False

                if (img_bbox[1] > page_height * IGNORE_IMAGE_THRESHOLD) or (img_bbox[1] <= HEADER_FOOTER_THRESHOLD) or (
                    img_bbox[3] >= page_height - HEADER_FOOTER_THRESHOLD): # check if the img position is in the bottom 30% of the image, and ignores it
                    cprint.yellow(f"ignored image {img_filename} bbox: {img_bbox} ")
                    ignored = True
                    # continue

                # if image is an xref
                if isinstance(img_data, int):
                    xref = img_data
                    if xref == 0:
                        continue
                    
                    pix = extract_img_from_xref(doc, xref)
                    if not ignored: images[img_filename] = pix.tobytes()
                    else: ignored_images[img_filename] = hashlib.md5(pix.tobytes()).hexdigest()
                    pix = None
                elif isinstance(img_data, bytes): # otherwise it's the raw data
                    if not ignored: images[img_filename] = img_data
                    else: ignored_images[img_filename] = hashlib.md5(img_data).hexdigest()
                else:
                    cprint.red("Image not recognized!")
                    continue

                if not ignored:
                    content += f'<img src="test_images/{img_filename}" alt="Image {img_count} on page {i+1}" />\n'
            else:
                cprint.red(f"Error: unrecognized block type {element["type"]}")

        # check if there are any missed images
        # TODO Check for duplicate images
        if img_count < get_images_count:
            cprint.red(f"Missed {get_images_count - img_count} images. Extracting and checking duplicates...")

            rev_ignored_images = {}
            for key, value in ignored_images.items():
                rev_ignored_images.setdefault(value, set()).add(key)
            
            rev_images = {}
            for key, value in images.items():
                rev_images.setdefault(hashlib.md5(value).hexdigest(), set()).add(key)
            
            for index, img in enumerate(img_list):
                xref = img[0]
                image_rects = page.get_image_rects(xref)[0] # this returns (x0, y0, x1, y1)
                image_height = image_rects[3] - image_rects[1]
                full_img_filename = f"page_{i+1}-full_{index}.png"

                if xref == 0:
                    continue
                # image thresholds
                if (image_rects[1] > page_height * IGNORE_IMAGE_THRESHOLD) or (image_height < 5):
                    continue 

                pix = extract_img_from_xref(doc, img[0])
                full_img_bytes = pix.tobytes()

                # check duplicates
                img_hash = hashlib.md5(full_img_bytes).hexdigest()
                if img_hash in rev_ignored_images or img_hash in rev_images:
                    #! PROBLEM: get_images hash and get_text("dicts") hash is different.
                    # use with tomodare (has 2 square images at the start of each page, in header) 
                    # still ignores said  images because it detects those from the first page 
                    # and gets caught in the (img_hash in rev_images). maybe this is fine maybe not. 
                    # idk how to compare them now tbh
                    # maybe use a comparing algo but that'll probably be too slow
                    duplicate_filename = rev_ignored_images[img_hash] if img_hash in rev_ignored_images else rev_images[img_hash]
                    cprint.black(f"Detected already ignored image: {full_img_filename} duplicate with {duplicate_filename}")
                    continue

                images[full_img_filename] = full_img_bytes
                content += f'<img src="test_images/{full_img_filename}" alt="Full Image {index} on page {i+1}" />\n'

    return content, images

# pdf_path = "test_pdf/Gunatsu Volume 1.pdf"
# pdf_path = "test_pdf/Like Snow Piling.pdf"
# pdf_path = "test_pdf/StartingOver.pdf"
pdf_path = "test_pdf/Tomodare1.pdf"
doc = pymupdf.open(pdf_path)
pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]

result = extract_pdf(doc)

# save images
for i, (key, value) in enumerate(result[1].items()):
    # print(i, key)
    with open(f"test_output/test_images/{key}", "wb") as f:
        f.write(value)
cprint.cyan(f"Saved images to test_output/test_images/")

# save result html
with open(f"test_output/output-{pdf_filename}.html", "w", encoding="utf-8") as f:
    f.write(result[0])
    
cprint.cyan(f"\nSaved output to test_output/output-{pdf_filename}.html")
cprint.green("Done")