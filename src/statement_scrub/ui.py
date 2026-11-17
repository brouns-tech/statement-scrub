"""Local, PDF-first review with conservative automatic replacement suggestions."""
import hashlib
import json
from io import BytesIO
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates
from statement_scrub.editing import edit_pdf, hit_test, drag_region, fields_in_region

import streamlit as st

from statement_scrub.pdf import extract, preview, highlighted_preview, build_candidate
from statement_scrub.scenario import generate
from statement_scrub.detection import suggest, needs_review, status, priority, is_date, is_amount, static_allowed


def prepare(data, seed=42, year=2025, count=0):
    doc = extract(data)
    if not count:
        count = max(1, min(200, max(sum(is_date(f.text) for f in doc.fragments),
                                  sum(is_amount(f.text) for f in doc.fragments))))
    values = generate(int(seed), int(count), int(year))
    rows = suggest(doc, values)
    return doc, values, rows


def main():
    st.set_page_config(page_title='Statement Scrub', page_icon='🧽', layout='wide')
    st.title('Statement Scrub')
    st.caption('Replace private financial data locally. Review the changes before sharing.')
    # Native flex wrapping: compact on wide screens, stacked and clamped on narrow ones.
    with st.container(horizontal=True, width=840, gap='medium', key='document_setup'):
        with st.container(border=True, width=400):
            uploaded = st.file_uploader('Choose a financial document', type=['pdf'], key='upload')
            start = st.button('Anonymise', type='primary', disabled=uploaded is None, use_container_width=True)
        with st.container(width=400):
            with st.expander('Optional synthetic settings', expanded=False):
                st.caption('Defaults work without changes. Adjust these only if you want additional control.')
                seed = st.number_input('Synthetic seed', min_value=0, max_value=1000000, value=42,
                                       help='Controls fictional values; never derived from the document.')
                year = st.number_input('Synthetic reporting year', min_value=2000, max_value=2099, value=2025,
                                       help='Year used for fictional dates. Original transaction dates are replaced.')
                count = st.number_input('Transaction count (0 = detect)', min_value=0, max_value=200, value=0,
                                        help='Zero estimates the scenario size from recognised dates and amounts; otherwise use this many fictional transactions.')
                st.caption('Applied when you click Anonymise.')
    if start:
        try:
            data = uploaded.getvalue()
            doc, values, rows = prepare(data,seed,year,count)
        except Exception:
            st.error('Cannot process this PDF. Use an unencrypted, text-based PDF within the supported limits.')
        else:
            for key in list(st.session_state):
                if key.startswith(('review-', 'field-', 'detail-', 'edit-', 'candidate')):
                    del st.session_state[key]
            st.session_state.update(document=doc, source=data, values=values, rows=rows, revision=0, regions=[], selected_id=None)
    if 'document' not in st.session_state:
        st.write('Choose a PDF and click Anonymise. Recognised fields are replaced automatically; uncertain text is highlighted for review.')
        st.caption('Runs on this computer. Documents are not sent to an external service.')
        return
    if uploaded is not None and uploaded.getvalue() != st.session_state.source:
        st.info('Click Anonymise to process the newly selected document. Previous results are hidden until then.')
        return
    doc, rows, values = st.session_state.document, st.session_state.rows, st.session_state['values']
    st.divider()
    st.subheader('Review changes')
    replacements = sum(r['action']=='replace' for r in rows)
    remaining = sum(needs_review(r) for r in rows)
    a,b,c = st.columns(3)
    a.metric('Replacements', replacements)
    b.metric('Needs review', remaining)
    c.metric('Pages', len(doc.pages))
    st.caption('Green: replaced · Amber: needs review · Grey: kept/omitted · Blue outline: selected field. '
               '“Replaced” describes the field, not approval of the entire document.')
    page = st.selectbox('Page', range(len(doc.pages)),format_func=lambda n:f'Page {n+1}')
    page_rows = sorted([r for r in rows if r['page']==page+1], key=priority)
    revision = st.session_state.get('revision',0)
    control, visual = st.columns([1,3],gap='large')
    with control:
        unresolved_only = st.checkbox('Only fields needing review', value=True)
        choices = [r for r in page_rows if needs_review(r) or r['id']==st.session_state.get('selected_id')] if unresolved_only else page_rows
        selected = None
        if choices:
            selected = st.selectbox('Field · highest priority first', [r['id'] for r in choices],
                                    format_func=lambda key: next(f"{r['id']} · {r['kind']}" for r in choices if r['id']==key),
                                    key=f'field-select-{page}-{revision}',
                                    index=next((i for i,r in enumerate(choices) if r['id']==st.session_state.get('selected_id')),0))
            row = next(r for r in rows if r['id']==selected)
            st.caption(status(row))
            st.text(row['source'])
            action = st.selectbox('Decision',['pending','replace','static','drop'],
                                  index=['pending','replace','static','drop'].index(row['action']),
                                  key=f'field-action-{selected}-{revision}',
                                  format_func=lambda x:{'pending':'Needs review','replace':'Replace','static':'Keep generic label','drop':'Omit'}[x])
            options = ['']+list(values)
            key = st.selectbox('Synthetic field',options,index=options.index(row['replacement']) if row['replacement'] in options else 0,
                               key=f'field-value-{selected}-{revision}',disabled=action!='replace')
            if action=='replace':
                replacement_text=st.text_input('Replacement text',value=values.get(key,''),
                                               key=f'field-text-{selected}-{revision}-{key}',
                                               help='Edit the fictional value that will appear at this position in the PDF.')
            width = st.number_input('Available width (points)',min_value=1.0,max_value=2000.0,
                                    value=float(row['width']),key=f'field-width-{selected}-{revision}')
            if st.button('Apply and confirm',disabled=action=='pending' or (action=='replace' and not key)):
                if action=='static' and not static_allowed(row['source']):
                    st.error('Numbers and identifiers must be replaced or omitted.')
                else:
                    if action=='replace' and replacement_text!=values.get(key,''):
                        key='custom.'+selected
                        values[key]=replacement_text
                    row.update(action=action,replacement=key,width=width,review_required=False)
                    st.session_state.selected_id=selected
                    st.session_state.revision=revision+1
                    st.rerun()
        else:
            st.success('No unresolved fields on this page.')
        st.caption(row.get('reason','') if choices else 'All typed fields are resolved. Inspect every page before export.')
    with visual:
        original, reconstructed = st.tabs(['PDF · click to edit','Edited PDF'])
        with original:
            mode=st.radio('PDF interaction',['Select text','Redact a region'],horizontal=True,
                          help='Click text to edit its replacement. Drag a region to remove an image, signature or other private content.')
            img=Image.open(BytesIO(highlighted_preview(st.session_state.source,doc,rows,page,selected)))
            event=streamlit_image_coordinates(img,width='stretch',key=f'pdf-click-{page}-{mode}',
                                             click_and_drag=mode=='Redact a region',cursor='crosshair')
            if event and event.get('unix_time')!=st.session_state.get('last_click'):
                st.session_state.last_click=event.get('unix_time')
                if mode=='Select text':
                    hit=hit_test(doc,page,event['x'],event['y'],event['width'],event['height'])
                    if hit:
                        st.session_state.selected_id=hit
                        st.session_state.revision=revision+1
                        st.rerun()
                else:
                    region=drag_region(doc,page,event)
                    if region:
                        affected=fields_in_region(doc,region)
                        region['previous_rows']=[dict(r) for r in rows if r['id'] in affected]
                        for r in rows:
                            if r['id'] in affected:r.update(action='drop',review_required=False)
                        st.session_state.setdefault('regions',[]).append(region)
                        st.session_state.revision=revision+1
                        st.rerun()
            if st.session_state.get('regions'):
                st.caption(f"{len(st.session_state.regions)} manual region redactions queued. Inspect them in Edited PDF.")
                if st.button('Undo last region redaction'):
                    last=st.session_state.regions.pop()
                    previous={r['id']:r for r in last.get('previous_rows',[])}
                    st.session_state.rows=[previous.get(r['id'],r) for r in rows]
                    st.session_state.revision=revision+1;st.rerun()
            st.caption('Original with review highlights: click text to select it. This view still contains private data.')
        with reconstructed:
            fingerprint = hashlib.sha256(json.dumps([rows,values,st.session_state.get("regions",[])],sort_keys=True).encode()).hexdigest()
            if st.session_state.get('candidate_key')!=fingerprint:
                st.session_state.pop('candidate',None)
                st.session_state.pop('candidate_error',None)
                st.session_state.pop('edit_report',None)
                preview_rows = rows
                try:
                    st.session_state.candidate,st.session_state.edit_report=edit_pdf(
                        st.session_state.source,doc,preview_rows,values,st.session_state.get('regions',[]),draft=True)
                except ValueError as exc:
                    st.session_state.candidate_error=str(exc)
                except Exception:
                    st.session_state.candidate_error='Preview generation failed. No output can be exported.'
                st.session_state.candidate_key=fingerprint
                newly_blocked=False
                for r in rows:
                    problem=st.session_state.get('edit_report',{}).get('blocked_fields',{}).get(r['id'])
                    if problem and (not r.get('review_required') or r.get('reason')!=problem):
                        r.update(review_required=True,reason=problem);newly_blocked=True
                if newly_blocked:st.rerun()
            if 'candidate' in st.session_state:
                st.image(preview(st.session_state.candidate,page),use_container_width=True)
                st.caption('Draft: unresolved text remains visible. Original layout and untouched fonts are preserved; replacements reuse embedded fonts where possible.')
                st.caption(f"{len(st.session_state.get('edit_report',{}).get('font_fallbacks',[]))} font fallbacks; {len(st.session_state.get('edit_report',{}).get('blocked_fields',{}))} fields could not be replaced and remain original in this draft.")
            else:
                st.info(st.session_state.get('candidate_error','Resolve fields to create a preview.'))
    with st.expander('Detailed field review · unresolved first',expanded=False):
        detailed = [{**r,'status':status(r),'synthetic_value':values.get(r['replacement'],'')} for r in page_rows]
        edited = st.data_editor(detailed,hide_index=True,num_rows='fixed',use_container_width=True,
                               key=f'detail-{page}-{revision}',
                               column_order=['status','kind','source','synthetic_value','action','replacement','review_required','width','id'],
                               disabled=['id','page','source','kind','status','synthetic_value'],
                               column_config={
                                   'action':st.column_config.SelectboxColumn(options=['pending','replace','static','drop'],required=True),
                                   'replacement':st.column_config.SelectboxColumn(options=['']+list(values)),
                                   'review_required':st.column_config.CheckboxColumn('Needs review',required=True),
                                   'width':st.column_config.NumberColumn(min_value=1,max_value=2000),
                               })
        if st.button('Apply detailed edits'):
            edits={r['id']:r for r in edited}
            st.session_state.rows=[{k:v for k,v in edits.get(r['id'],r).items() if k not in ('status','synthetic_value')} for r in rows]
            st.session_state.revision=revision+1
            st.rerun()
    st.subheader('Export reviewed PDF')
    unsupported_text=doc.omitted_rotated_chars>0
    if unsupported_text:
        st.warning('This document has rotated text not represented by editable fields. Export is blocked until rotated-text support is added.')
    st.caption('Images and graphics are preserved. Review them and redact private regions. Attachments, annotations, forms, links and metadata are removed.')
    reconciled=st.checkbox('I checked balances, totals and transaction relationships in the edited document',
                           key=f'review-ledger-{fingerprint}',
                           help='Recognising money and dates does not establish their accounting roles. Review the document-level reconciliation before sharing.')
    reviewed = st.checkbox('I checked this page in Edited PDF, including text, images and region redactions',
                           key=f'review-page-{fingerprint}-{page}',disabled=remaining>0 or 'candidate' not in st.session_state)
    checked = all(st.session_state.get(f'review-page-{fingerprint}-{i}',False) for i in range(len(doc.pages)))
    st.download_button('Download reviewed synthetic PDF',st.session_state.get('candidate',b''),
                       file_name='synthetic-statement.pdf',mime='application/pdf',
                       disabled=remaining>0 or not checked or not reconciled or unsupported_text or 'candidate' not in st.session_state)
    if remaining:
        st.caption(f'Resolve {remaining} fields before approving pages and downloading.')


if __name__=='__main__':
    main()
