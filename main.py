import ColorPrint as cprint
import pymupdf
from ebooklib import epub
import os
import hashlib

os.makedirs("test_output/images", exist_ok=True)
HEADER_FOOTER_THRESHOLD = 70 # threshold for the text extraction. may need to change for every document
IGNORE_IMAGE_THRESHOLD = 0.7 # only extract images in this top % of the page. for example 0.7 ignores the bottom 30% (0.3) of the page

def debug_print(level, i, text):
    page = i + 1
    page_debug = f"PAGE {page:3}"
    print_text = f"{page_debug:<9} {text}"
    if level == "info":
        cprint.lightgrey(print_text)
    elif level == "error":
        cprint.red(print_text)
    elif level == "warning":
        cprint.yellow(print_text)
    # elif level == "debug":
    #     cprint.black(print_text)
    elif level == "success":
        cprint.green(print_text)


# TODO use first image as cover
# TODO this is still copied from epubscraper
def create_epub(chapters, output_filename, title, author, cover_image=None):
    cprint.green("Creating EPUB...")
    book = epub.EpubBook()
    book.set_identifier("")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
    if cover_image:
        book.set_cover(cover_image[0], cover_image[1])
    
    epub_chapters = []
    
    for i, (content, images) in enumerate(chapters):
        chapter = epub.EpubHtml(title=title, file_name=f'chapter_{i}.xhtml', lang='en')
        chapter.content = content
        epub_chapters.append(chapter)
        book.add_item(chapter)
        
        # Add images to the book
        for img_name, img_data in images.items():
            img_item = epub.EpubItem(uid=img_name, file_name=f'images/{img_name}', media_type='image/jpeg', content=img_data)
            book.add_item(img_item)
    
    # Define the book spine and TOC
    book.toc = epub_chapters
    book.spine = ['nav'] + epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Write the EPUB file
    epub.write_epub(output_filename, book)
    cprint.cyan(f"\nEPUB file '{output_filename}' created successfully.\n")

def split_to_chapters(doc, extracted_content):
    full_text, images = extracted_content
    toc = doc.get_toc()
    if not toc:
        cprint.red("Table of contents not found. This book will not have any TOC.")
        return [extracted_content]
    # TODO use TOC to split chapters
    return [extracted_content]

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

    for i in range(start, end):
        page = doc[i]
        page_height = page.rect.height
        dicts = page.get_text("dict", sort=True)
        img_count = 0
        img_list = page.get_images()
        get_images_count = len(img_list)
        ignored_images = set()

        for element in dicts["blocks"]:
            if element["type"] == 0: # text block
                # ignore text blocks in headers and footers
                if element["bbox"][1] <= HEADER_FOOTER_THRESHOLD or element["bbox"][1] >= page_height - HEADER_FOOTER_THRESHOLD:
                    continue
                content += extract_text_from_lines(element["lines"])
            
            elif element["type"] == 1: # image
                img_count += 1
                img_data = element["image"]
                img_bbox = element["bbox"]
                # img_height =  img_bbox[3] - img_bbox[1]
                img_filename = f"page_{i+1}-image_{img_count}.png"

                # ignores images in headers and bottom part of the page (use threshold)
                if (img_bbox[1] > page_height * IGNORE_IMAGE_THRESHOLD) or (img_bbox[1] <= HEADER_FOOTER_THRESHOLD): 
                    debug_print("debug", i, f"ignored image {img_filename} bbox: {img_bbox}")
                    ignored_images.add(img_bbox)
                    continue

                # if image is an xref
                if isinstance(img_data, int):
                    xref = img_data
                    if xref == 0:
                        continue
                    
                    pix = extract_img_from_xref(doc, xref)
                    images[img_filename] = pix.tobytes()
                    pix = None
                elif isinstance(img_data, bytes): # otherwise it's the byte data
                    images[img_filename] = img_data
                else:
                    debug_print("error", i, f"Image not recognized! Img data: \n{img_data}")
                    continue

                content += f'<img src="images/{img_filename}" alt="Image {img_count} on page {i+1}" />\n'
            else:
                debug_print("error", i, f"Error: unrecognized block type {element["type"]}")

        # check if there are any missed images
        if img_count < get_images_count:
            debug_print("debug", i, f"Missed {get_images_count - img_count} images. Extracting and checking duplicates...")

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
                if (image_rects in ignored_images):
                    continue
                
                debug_print("info", i, f"Adding missing image: {full_img_filename}")
                images[full_img_filename] = full_img_bytes
                content += f'<img src="images/{full_img_filename}" alt="Full Image {index} on page {i+1}" />\n'

    return content, images

def pdf_to_epub(doc):
    pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    cprint.cyan(f"Processing {pdf_filename}")
    result = extract_pdf(doc)

    # save images
    for i, (key, value) in enumerate(result[1].items()):
        # print(i, key)
        with open(f"test_output/images/{key}", "wb") as f:
            f.write(value)
    cprint.cyan(f"Saved images to test_output/images/")

    # save result html
    with open(f"test_output/output-{pdf_filename}.html", "w", encoding="utf-8") as f:
        f.write(result[0])
        
    cprint.cyan(f"\nSaved HTML output to test_output/output-{pdf_filename}.html\n")

    chapters = split_to_chapters(doc, result)
    cover_image_name = next(iter(result[1].keys()))
    cover_image_data = result[1][cover_image_name]

    create_epub(chapters, f"test_output/{pdf_filename}.epub", pdf_filename, "", (cover_image_name, cover_image_data))

# pdf_path = "test_pdf/Gunatsu Volume 1.pdf"
# pdf_path = "test_pdf/Like Snow Piling.pdf"
# pdf_path = "test_pdf/StartingOver.pdf"
pdf_path = "test_pdf/Tomodare1.pdf"
doc = pymupdf.open(pdf_path)
pdf_to_epub(doc)

pdf_path = "test_pdf/Tomodare2.pdf"
doc = pymupdf.open(pdf_path)
pdf_to_epub(doc)

pdf_path = "test_pdf/Tomodare3.pdf"
doc = pymupdf.open(pdf_path)
pdf_to_epub(doc)

cprint.green("Done")