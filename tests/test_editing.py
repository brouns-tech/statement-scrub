from io import BytesIO
from pathlib import Path
import pytest
import pymupdf as fitz
from pypdf import PdfReader,PdfWriter
from pypdf.annotations import Text
from reportlab.pdfgen import canvas
from statement_scrub.pdf import extract,draft_rows,preview
from statement_scrub.demo import demo_pdf
from statement_scrub.scenario import generate
from statement_scrub.editing import edit_pdf,hit_test,drag_region,fields_in_region
from statement_scrub.detection import suggest,needs_review,is_date,is_amount


def test_direct_removal_hidden_objects_and_preserved_layout():
    stream=BytesIO();c=canvas.Canvas(stream)
    c.setFont('Helvetica-Bold',12);c.drawString(40,740,'Generic header')
    c.setFont('Helvetica',12);c.drawString(40,700,'SECRET_VALUE')
    c.line(40,680,500,680);c.save()
    w=PdfWriter(clone_from=BytesIO(stream.getvalue()))
    w.add_metadata({'/Title':'SECRET_METADATA'})
    w.add_attachment('secret.txt',b'SECRET_ATTACHMENT')
    w.add_annotation(0,Text(rect=(5,5,15,15),text='SECRET_ANNOTATION'))
    b=BytesIO();w.write(b);source=b.getvalue();d=extract(source);rows=draft_rows(d)
    for r in rows:
        r.update(action='replace' if 'SECRET' in r['source'] else 'static',replacement='identity.name',review_required=False)
    result,report=edit_pdf(source,d,rows,generate())
    r=PdfReader(BytesIO(result));text=r.pages[0].extract_text()
    assert 'SECRET' not in text and 'FICTIEVE PERSOON' in text and 'Generic header' in text
    assert not r.attachments and not r.pages[0].get('/Annots')
    assert 'SECRET' not in str(r.metadata)
    with fitz.open(stream=result,filetype='pdf') as doc:
        assert doc[0].get_drawings() # original line survives
        spans=[s for b in doc[0].get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
        heading=next(s for s in spans if s['text']=='Generic header')
        assert heading['font']=='Helvetica-Bold'
        for i in range(1,doc.xref_length()):
            assert 'SECRET_' not in doc.xref_object(i)
            if doc.xref_is_stream(i):assert b'SECRET_' not in doc.xref_stream(i)
    assert source==b.getvalue()
    assert report['replaced_or_removed']==1


def test_embedded_font_reuse():
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font_path=Path(reportlab.__file__).parent/'fonts'/'Vera.ttf'
    with fitz.open() as source:
        page=source.new_page()
        page.insert_font(fontname='FullVera',fontfile=str(font_path))
        page.insert_text((40,80),'ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789',fontname='FullVera',fontsize=12)
        page.insert_text((40,120),'PRIVATE',fontname='FullVera',fontsize=12)
        data=source.tobytes()
    d=extract(data);rows=draft_rows(d)
    for r in rows:r.update(action='replace',replacement='identity.reference',review_required=False)
    # Characters all exist in the source subset.
    out,report=edit_pdf(data,d,rows,{'identity.reference':'TEST'})
    assert not report['font_fallbacks']
    assert 'PRIVATE' not in PdfReader(BytesIO(out)).pages[0].extract_text()


def test_click_coordinates_and_region_redaction():
    source=demo_pdf();d=extract(source);f=d.fragments[0];pw,ph=d.pages[0]
    assert hit_test(d,0,(f.x+2)/pw*400,(ph-f.y-2)/ph*600,400,600)==f.id
    region=drag_region(d,0,{'x1':0,'y1':0,'x2':400,'y2':100,'width':400,'height':600})
    assert f.id in fields_in_region(d,region)
    rows=draft_rows(d)
    for r in rows:r.update(action='drop',review_required=False)
    rows[0]['action']='static'
    out,_=edit_pdf(source,d,rows,generate(),[region])
    assert f.text not in PdfReader(BytesIO(out)).pages[0].extract_text()


def test_unresolved_blocks_real_export_but_draft_preserves_context():
    source=demo_pdf();d=extract(source);rows=draft_rows(d)
    with pytest.raises(ValueError,match='Resolve'):
        edit_pdf(source,d,rows,generate())
    out,_=edit_pdf(source,d,rows,generate(),draft=True)
    assert 'DEMO PERSOON' in PdfReader(BytesIO(out)).pages[0].extract_text()


def document_with_lines(lines):
    b=BytesIO();c=canvas.Canvas(b)
    for x,y,text in lines:c.drawString(x,y,text)
    c.save();return extract(b.getvalue())


def test_sensitive_context_beats_keyword_and_generic_labels_survive():
    d=document_with_lines([(40,740,'Naam'),(220,740,'Datum'),(40,700,'Betaalrekening'),(40,670,'BETALING'),(40,640,'Pagina 1 van 2')])
    rows=suggest(d,generate())
    datum=next(r for r in rows if r['source']=='Datum')
    assert datum['action']=='replace' and datum['replacement']=='identity.name'
    assert next(r for r in rows if r['source']=='Betaalrekening')['action']=='static'
    assert next(r for r in rows if r['source']=='BETALING')['action']=='static'
    assert next(r for r in rows if r['source'].startswith('Pagina'))['kind']=='Pagination'


@pytest.mark.parametrize('text',['1.234,00','€ 100','EUR 1.234,00','1234.50','$ 1,234.56','-12,34'])
def test_generic_money_formats(text):assert is_amount(text)


@pytest.mark.parametrize('text',['31-02-2025','99-99','2025-02-30'])
def test_invalid_calendar_dates(text):assert not is_date(text)


def test_generic_identifiers_phone_and_street():
    # Published library/example numbering; no private data.
    d=document_with_lines([(40,740,'BIC: ABNANL2A'),(40,700,'+31 20 123 4567'),(40,660,'Voorbeeldstraat 12')])
    rows=suggest(d,generate())
    assert [r['kind'] for r in rows]==['BIC','Phone number','Street address']
    assert all(not needs_review(r) for r in rows)


def test_non_fitting_replacement_keeps_original_in_draft_but_cannot_export():
    d=document_with_lines([(40,740,'PRIVATE')])
    b=BytesIO();c=canvas.Canvas(b);c.drawString(40,740,'PRIVATE');c.save()
    rows=draft_rows(d);rows[0].update(action='replace',replacement='test',review_required=False,width=2)
    out,report=edit_pdf(b.getvalue(),d,rows,{'test':'LONG REPLACEMENT'},draft=True)
    assert rows[0]['id'] in report['blocked_fields']
    assert 'PRIVATE' in PdfReader(BytesIO(out)).pages[0].extract_text()
    with pytest.raises(ValueError):edit_pdf(b.getvalue(),d,rows,{'test':'LONG REPLACEMENT'})


def test_numeric_static_cannot_bypass_export_policy():
    b=BytesIO();c=canvas.Canvas(b);c.drawString(40,740,'100,00');c.save()
    d=extract(b.getvalue());rows=draft_rows(d)
    rows[0].update(action='static',review_required=False)
    with pytest.raises(ValueError,match='cannot be kept'):
        edit_pdf(b.getvalue(),d,rows,generate())
