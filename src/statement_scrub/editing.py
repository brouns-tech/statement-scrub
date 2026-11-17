"""Destructive redaction and font-aware insertion on a disposable copy of the PDF.

PyMuPDF handles PDF content removal. No incremental saves or reversible mappings.
"""
from __future__ import annotations
import math
import re
import pymupdf as fitz
from statement_scrub.pdf import LOCK


def rect_for(fragment,height):
    return fitz.Rect(fragment.x-.15,height-(fragment.top or fragment.y+fragment.size)-.15,
                     fragment.x+fragment.ink_width+.15,height-(fragment.bottom or fragment.y-fragment.size*.25)+.15)


def hit_test(document,page,x,y,width,height):
    if width<=0 or height<=0:return None
    pw,ph=document.pages[page]
    px,py=x/width*pw,y/height*ph
    choices=[]
    for f in document.fragments:
        if f.page!=page:continue
        r=rect_for(f,ph)
        if (r+(-3,-3,3,3)).contains(fitz.Point(px,py)):
            choices.append((r.get_area(),f.id))
    return min(choices)[1] if choices else None


def drag_region(document,page,event):
    pw,ph=document.pages[page]
    x1,x2=sorted([max(0,min(pw,event[k]/event['width']*pw)) for k in ['x1','x2']])
    y1,y2=sorted([max(0,min(ph,event[k]/event['height']*ph)) for k in ['y1','y2']])
    if x2-x1<2 or y2-y1<2:return None
    return {'page':page,'rect':[x1,y1,x2,y2]}


def edit_pdf(source,document,rows,values,regions=(),draft=False):
    from statement_scrub.detection import needs_review,static_allowed
    if not draft and document.omitted_rotated_chars:
        raise ValueError('Rotated text is not yet covered by editable fields.')
    if not draft and any(needs_review(r) for r in rows):
        raise ValueError('Resolve all fields before export.')
    if len(rows)!=len(document.fragments) or {r['id'] for r in rows}!={f.id for f in document.fragments}:
        raise ValueError('Every field requires exactly one decision.')
    by_id={r['id']:r for r in rows};fallbacks=[];changes=0;blocked={}
    with LOCK,fitz.open(stream=source,filetype='pdf') as doc:
        if doc.is_encrypted:raise ValueError('Encrypted PDFs are unsupported.')
        if doc.get_ocgs():raise ValueError('Layered PDFs require a separate sanitisation workflow.')
        doc.scrub()  # metadata, attachments, scripts, hidden text, links and form values
        doc.set_toc([])
        root=doc.pdf_catalog()
        for key in ['Names','Metadata','OpenAction','AA','AcroForm','Outlines','StructTreeRoot','MarkInfo','PieceInfo','Perms','Collection']:
            doc.xref_set_key(root,key,'null')
        for page_number,page in enumerate(doc):
            for widget in list(page.widgets() or []):page.delete_widget(widget)
            for annot in list(page.annots() or []):page.delete_annot(annot)
            for key in ['Metadata','PieceInfo','AA']:
                doc.xref_set_key(page.xref,key,'null')
            spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
            fonts=page.get_fonts(full=True)
            inserts=[]
            page_regions=[fitz.Rect(r['rect']) for r in regions if r['page']==page_number]
            for f in document.fragments:
                if f.page!=page_number:continue
                row=by_id[f.id]
                area=rect_for(f,document.pages[page_number][1])
                if any(area.intersects(r) for r in page_regions):
                    page.add_redact_annot(area,fill=False,cross_out=False);changes+=1;continue
                if row['action']=='static' and not static_allowed(f.text):
                    raise ValueError(f'{f.id}: numeric/identifier-like content cannot be kept; replace or omit it.')
                if row['action'] in ('pending','static'):continue
                if row['action'] not in ('drop','replace'):raise ValueError('Unknown field decision.')
                if row['action']=='drop':
                    page.add_redact_annot(area,fill=False,cross_out=False);changes+=1;continue
                if row['replacement'] not in values:raise ValueError(f'{f.id}: choose a replacement.')
                text=values[row['replacement']]
                if not text:
                    page.add_redact_annot(area,fill=False,cross_out=False);changes+=1;continue
                overlapping=[s for s in spans if fitz.Rect(s['bbox']).intersects(area)]
                span=max(overlapping,key=lambda s:(fitz.Rect(s['bbox'])&area).get_area(),default={})
                name=span.get('font','Helvetica');size=span.get('size',f.size)
                colour=span.get('color',0);color=((colour>>16&255)/255,(colour>>8&255)/255,(colour&255)/255)
                normal_font=lambda value:re.sub(r'[^a-z0-9]','',value.split('+')[-1].casefold())
                matched=next((font for font in fonts if normal_font(font[3])==normal_font(name)),None)
                buffer=b'';font=None
                if matched:
                    try:
                        buffer=doc.extract_font(matched[0])[3]
                        if buffer:
                            font=fitz.Font(fontbuffer=buffer)
                            if not all(font.has_glyph(ord(c)) for c in text):font=None
                    except Exception:font=None
                if font is not None:
                    resource=f'Scrub{len(inserts)}'
                    pass  # Register after redaction, which cleans unused resources.
                else:
                    lower=name.lower();bold='bold' in lower;italic=any(s in lower for s in ['italic','oblique'])
                    family='cour' if 'cour' in lower else 'tiro' if 'times' in lower else 'helv'
                    resource={'helv':['helv','hebo','heit','hebi'],'cour':['cour','cobo','coit','cobi'],'tiro':['tiro','tibo','tiit','tibi']}[family][int(bold)+2*int(italic)]
                    font=fitz.Font(resource)
                    buffer=b''
                    fallbacks.append(f.id)
                available=float(row['width'])
                if not math.isfinite(available) or available<=0 or f.x+available>page.rect.width+.5:
                    raise ValueError(f'{f.id}: invalid replacement width.')
                size=min(size,available/max(font.text_length(text,fontsize=1),.01))
                if size<5 or not all(font.has_glyph(ord(c)) for c in text):
                    if draft:
                        blocked[f.id]='Replacement does not fit or font lacks characters; adjust text/width.';continue
                    raise ValueError(f'{f.id}: replacement does not fit or contains unsupported glyphs.')
                origin=fitz.Point(f.x,document.pages[page_number][1]-f.y)
                box=fitz.Rect(origin.x,origin.y-size,origin.x+font.text_length(text,fontsize=size),origin.y+size*.3)
                # Do not overwrite text in a neighbouring field to make a replacement fit.
                overlap=False
                for g in document.fragments:
                    if g.page==f.page and g.id!=f.id and by_id[g.id]['action'] not in ('drop',):
                        other=rect_for(g,document.pages[f.page][1])
                        if box.intersects(other) and not area.intersects(other) and (box&other).get_area()>2:
                            overlap=True;break
                if overlap:
                    if draft:
                        blocked[f.id]='Replacement overlaps another field; adjust text/width.';continue
                    raise ValueError(f'{f.id}: replacement overlaps another field.')
                page.add_redact_annot(area,fill=False,cross_out=False);changes+=1
                inserts.append((origin,text,size,resource,color,buffer))
            # Region redactions also remove image pixels and overlapping line art.
            for region in page_regions:page.add_redact_annot(region,fill=(1,1,1),cross_out=False)
            page.apply_redactions(images=2,graphics=2,text=0)
            for origin,text,size,resource,color,buffer in inserts:
                if buffer:page.insert_font(fontname=resource,fontbuffer=buffer)
                page.insert_text(origin,text,fontsize=size,fontname=resource,color=color)
        doc.set_metadata({'title':'Synthetic financial fixture','author':'Statement Scrub',
                          'subject':'Fictional test data; reviewed replacement of financial values'})
        result=doc.tobytes(garbage=4,deflate=True,clean=True)
    with fitz.open(stream=result,filetype='pdf') as check:
        if check.embfile_count() or check.get_toc():raise ValueError('Unexpected embedded content.')
        for page in check:
            if list(page.annots() or []) or list(page.widgets() or []) or page.get_links():
                raise ValueError('Unexpected interactive content.')
    return result,{'replaced_or_removed':changes,'font_fallbacks':fallbacks,'blocked_fields':blocked}


def fields_in_region(document,region):
    box=fitz.Rect(region['rect'])
    return {f.id for f in document.fragments if f.page==region['page'] and
            rect_for(f,document.pages[f.page][1]).intersects(box)}
