from dataclasses import replace
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Text
from reportlab.pdfgen import canvas

from statement_scrub.demo import demo_pdf
from statement_scrub.pdf import extract, draft_rows, build_candidate, verify_clean_container, preview
from statement_scrub.scenario import generate


def amount(text):
    return Decimal(text.replace('.', '').replace(',', '.'))


def decisions(doc):
    roles = {'DEMO PERSOON': 'identity.name', 'NL00 DEMO 0000 0000 00': 'identity.account',
             '1.000,00': 'account.opening', '03-02-2025': 'tx.1.date',
             'DEMO BETALING': 'tx.1.description', '-100,00': 'tx.1.amount',
             '900,00': 'account.closing'}
    rows = draft_rows(doc)
    for row in rows:
        row['action'] = 'replace' if row['source'] in roles else 'static'
        row['replacement'] = roles.get(row['source'], '')
    return rows


def build(doc, rows=None, values=None):
    return build_candidate(doc, rows or decisions(doc), values or generate(count=1),
                           set(range(len(doc.pages))), True)


@pytest.mark.parametrize('seed,count,year', [(42,1,2025),(0,200,2024),(999,8,2026)])
def test_ledger_reconciles_and_dates_are_independent(seed,count,year):
    v=generate(seed,count,year)
    from datetime import datetime
    dates=[datetime.strptime(v[f'tx.{i}.date'],'%d-%m-%Y') for i in range(1,count+1)]
    assert dates == sorted(dates)
    balance=amount(v['account.opening'])
    for i in range(1,count+1):
        balance += amount(v[f'tx.{i}.amount'])
        assert balance == amount(v[f'tx.{i}.balance'])
    assert balance == amount(v['account.closing'])
    assert balance == amount(v['account.opening'])+amount(v['account.credits'])-amount(v['account.debits'])
    assert v==generate(seed,count,year)


def test_hidden_objects_and_original_values_do_not_carry_over():
    w=PdfWriter(clone_from=BytesIO(demo_pdf()))
    w.add_metadata({'/Title':'SECRET_METADATA'})
    w.add_attachment('secret.txt',b'SECRET_ATTACHMENT')
    w.add_annotation(0,Text(rect=(5,5,15,15),text='SECRET_ANNOTATION'))
    source=BytesIO(); w.write(source)
    doc=extract(source.getvalue())
    result=build(doc)
    r=PdfReader(BytesIO(result)); text=r.pages[0].extract_text()
    for secret in ['DEMO PERSOON','NL00 DEMO','03-02-2025','DEMO BETALING','-100,00']:
        assert secret not in text
    assert not r.attachments
    assert '/Annots' not in r.pages[0]
    assert 'SECRET' not in str(r.metadata)
    assert 'SECRET' not in repr(r.trailer)
    verify_clean_container(result)
    assert preview(result,0).startswith(b'\x89PNG')
    assert 'FICTIEVE PERSOON' in text


def test_unreviewed_pending_and_numeric_static_block_output():
    doc=extract(demo_pdf()); rows=draft_rows(doc)
    with pytest.raises(ValueError,match='Review every'):
        build_candidate(doc,rows,generate(),set(),True)
    with pytest.raises(ValueError,match='Acknowledge'):
        build_candidate(doc,rows,generate(),{0},False)
    with pytest.raises(ValueError,match='pending'):
        build(doc,rows)
    rows=decisions(doc)
    next(r for r in rows if r['source']=='1.000,00')['action']='static'
    with pytest.raises(ValueError,match='cannot be static'):
        build(doc,rows)


def test_fragment_identity_not_global_string_maps():
    b=BytesIO(); c=canvas.Canvas(b)
    c.drawString(40,700,'100,00'); c.drawString(40,650,'100,00'); c.save()
    doc=extract(b.getvalue()); rows=draft_rows(doc)
    for row,key in zip(rows,['account.opening','tx.1.amount']):
        row.update(action='replace',replacement=key)
    text=PdfReader(BytesIO(build(doc,rows))).pages[0].extract_text()
    v=generate(count=1)
    assert v['account.opening'] in text and v['tx.1.amount'] in text
    assert '100,00' not in text


def test_split_glyphs_are_never_implicitly_preserved():
    b=BytesIO(); c=canvas.Canvas(b)
    c.drawString(40,700,'100'); c.drawString(62,700,',00'); c.save()
    doc=extract(b.getvalue()); rows=draft_rows(doc)
    assert all(r['action']=='pending' for r in rows)
    for row in rows: row.update(action='replace',replacement='tx.1.amount')
    text=PdfReader(BytesIO(build(doc,rows))).pages[0].extract_text()
    assert '100' not in text


def test_reject_empty_scan_rotated_page_and_overflow():
    b=BytesIO(); c=canvas.Canvas(b); c.rect(40,40,50,50); c.showPage(); c.save()
    with pytest.raises(ValueError,match='no extractable'):
        extract(b.getvalue())
    doc=extract(demo_pdf()); rows=decisions(doc); rows[0]['width']=1
    with pytest.raises(ValueError,match='will not fit'):
        build(doc,rows)
    rows=decisions(doc); rows[0]['width']=float('nan')
    with pytest.raises(ValueError,match='outside'):
        build(doc,rows)
    w=PdfWriter(clone_from=BytesIO(demo_pdf())); w.pages[0].rotate(90)
    out=BytesIO();w.write(out)
    with pytest.raises(ValueError,match='Rotated pages'):
        extract(out.getvalue())


def test_complete_mapping_required_and_no_blank_export():
    doc=extract(demo_pdf()); rows=decisions(doc)
    with pytest.raises(ValueError,match='exactly one'):
        build(doc,rows[:-1])
    for r in rows:r['action']='drop'
    with pytest.raises(ValueError,match='empty'):
        build(doc,rows)


def test_rotated_marginal_text_is_omitted_and_reported():
    b=BytesIO(); c=canvas.Canvas(b)
    c.drawString(40,700,'Heading')
    c.saveState();c.translate(20,100);c.rotate(90);c.drawString(0,0,'SECRET_MARGIN');c.restoreState();c.save()
    doc=extract(b.getvalue())
    assert doc.omitted_rotated_chars > 0
    rows=draft_rows(doc)
    for r in rows:r['action']='static'
    result=build(doc,rows)
    assert 'SECRET' not in PdfReader(BytesIO(result)).pages[0].extract_text()


def test_ui_starts_without_loading_private_files(monkeypatch):
    monkeypatch.delenv('STATEMENT_SCRUB_SOURCE_DIR',raising=False)
    from streamlit.testing.v1 import AppTest
    import statement_scrub.ui as ui
    at=AppTest.from_file(ui.__file__).run(timeout=20)
    assert not at.exception
    assert at.title[0].value=='Statement Scrub'


def test_ui_requires_review_and_invalidates_candidate(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import statement_scrub.ui as ui
    at=AppTest.from_file(ui.__file__)
    doc=extract(demo_pdf())
    rows=decisions(doc)
    for row in rows:row.update(kind='Reviewed fixture',review_required=False)
    at.session_state['document']=doc
    at.session_state['source']=demo_pdf()
    at.session_state['rows']=rows
    at.session_state['values']=generate(count=1)
    at.session_state['revision']=0
    at.run(timeout=20)
    assert not at.exception
    assert at.session_state['candidate']
    old=at.session_state['candidate_key']
    review=next(c for c in at.checkbox if c.label.startswith('I checked this page'))
    review.check().run()
    assert not at.exception
    values=generate(seed=43,count=1)
    at.session_state['values']=values
    at.run()
    assert at.session_state['candidate_key']!=old
    assert not next(c for c in at.checkbox if c.label.startswith('I checked this page')).value


def test_single_picker_and_collapsed_details():
    from streamlit.testing.v1 import AppTest
    import statement_scrub.ui as ui
    at=AppTest.from_file(ui.__file__).run()
    assert not at.exception
    assert len(at.get('file_uploader'))==1
    assert not any('source folder' in s.label for s in at.selectbox)
    assert next(b for b in at.button if b.label=='Anonymise').disabled
    assert len(at.expander) == 1
    assert at.expander[0].label == 'Optional synthetic settings'
    assert not at.expander[0].proto.expanded
    assert len(at.number_input)==3
    assert all(n.proto.help for n in at.number_input)


def test_auto_replacements_use_whole_fragments_and_flag_uncertainty():
    from statement_scrub.detection import suggest,needs_review,priority
    from statement_scrub.pdf import Document,Fragment,highlighted_preview
    from stdnum import iban
    account='NL'+iban.calc_check_digits('NL00TEST0000000001')+'TEST0000000001'
    texts=[account,account,'1234 AB VOORBEELDSTAD','03-02','100,00','Unfamiliar person','Datum']
    doc=Document(((600,800),),tuple(Fragment(str(i),0,t,40,700-i*30,500,12) for i,t in enumerate(texts)),0)
    values=generate(count=3)
    rows=suggest(doc,values)
    assert rows[0]['action']=='replace' and not needs_review(rows[0])
    assert rows[0]['replacement']==rows[1]['replacement']
    assert values[rows[0]['replacement']]!=account
    assert rows[2]['action']=='replace' and not needs_review(rows[2])
    assert rows[3]['action']=='replace' and not needs_review(rows[3])
    assert rows[4]['action']=='replace' and not needs_review(rows[4])
    assert rows[5]['action']=='pending'
    assert sorted(rows,key=priority)[0] is rows[5]
    assert rows[6]['action']=='static'


def test_invalid_iban_does_not_get_complete_status():
    from statement_scrub.detection import suggest,needs_review
    from statement_scrub.pdf import Document,Fragment
    doc=Document(((600,800),),(Fragment('a',0,'NL00 TEST 0000 0000 01',40,700,500,12),),0)
    row=suggest(doc,generate())[0]
    assert row['action']=='replace' and needs_review(row)


def test_highlights_change_pixels_without_changing_source():
    from statement_scrub.pdf import highlighted_preview
    from statement_scrub.detection import suggest
    source=demo_pdf();doc=extract(source);rows=suggest(doc,generate())
    result=highlighted_preview(source,doc,rows,0,rows[0]['id'])
    assert result.startswith(b'\x89PNG')
    assert result!=preview(source,0,1.4)
    assert source==demo_pdf()
