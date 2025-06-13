import ColorPrint as cprint
import pymupdf
from ebooklib import epub

HEADER_FOOTER_THRESHOLD = 65

def create_epub():
    pass

def split_to_chapters(full_text):
    pass

# TODO change this to extract html. add the images in the html like from epubscraper
def extract_pdf(doc: pymupdf.Document):
    ignored_images = []
    content = ""

    for i in range(0, doc.page_count):
        cprint.blue(f"-----PAGE {i+1}------")
        page = doc[i]
        page_height = page.rect.height
        cprint.black(page_height)
        blocks = page.get_text("blocks")
        clean_text = ""

        # ignore header and footer with threshold
        for block in blocks:
            x0,y0,x1,y1,text, *_ =  block
            cprint.black(f"({x0}, {y0}) to ({x1}, {y1}): {text}")
            height = page.rect.height

            if y0 > HEADER_FOOTER_THRESHOLD and y0 < height - HEADER_FOOTER_THRESHOLD:
                clean_text += text + "\n"

        # print(page.get_text())
        print(clean_text)

        image_list = page.get_images()
        if image_list:
            cprint.cyan(f"Found {len(image_list)} images")
        
        # extract images
        for img_index, img in enumerate(image_list, start=1):
            xref = img[0]
            image_rects = page.get_image_rects(xref)[0] # this returns (x0, y0, x1, y1)
            image_height = image_rects[3] - image_rects[1]

            # check if the img position is in the bottom 30% of the image, and ignores it
            if (image_rects[1] > page_height * 0.7) or (image_height < 5): 
                cprint.yellow(f"Ignored image at page {i+1}_{img_index} position {image_rects}")
                ignored_images.append((i, xref))
                continue

            cprint.black(f"page {i+1} index {img_index} : {page.get_image_rects(xref)}")
            pix = pymupdf.Pixmap(doc, xref)

            if pix.n - pix.alpha > 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            
            pix.save(f"test_images/page_{i+1}-image_{img_index}.png")
            pix = None

    for ignored_index, ignored in enumerate(ignored_images):
        ignored_pix = pymupdf.Pixmap(doc, ignored[1])

        if ignored_pix.n - ignored_pix.alpha > 3:
            ignored_pix = pymupdf.Pixmap(pymupdf.csRGB, ignored_pix)

        ignored_pix.save(f"test_ignored_images/ignored_page_{ignored[0]}-image_{ignored_index}.png")
        # print(ignored)

doc = pymupdf.open("test_pdf/Gunatsu Volume 1.pdf")
# doc = pymupdf.open("test_pdf/Like Snow Piling.pdf")
# doc = pymupdf.open("test_pdf/RascalV1.pdf")
extract_pdf(doc)
cprint.green("Done")