"""Institution-independent financial rules with context before template vocabulary."""
import re
from datetime import datetime
import phonenumbers
from stdnum import iban, bic
from statement_scrub.pdf import draft_rows

IBAN = re.compile(r'\b[A-Z]{2}\s*\d{2}(?:[ ]?[A-Z0-9]){10,30}\b',re.I)
POSTCODE = re.compile(r'\b[1-9]\d{3}\s?[A-Z]{2}\b',re.I)
MONTHS = 'januari februari maart april mei juni juli augustus september oktober november december'.split()
DATE = re.compile(r'^\d{1,2}[-/.]\d{1,2}(?:[-/.]\d{2,4})?$')
LONG_DATE = re.compile(r'^(\d{1,2})\s+('+ '|'.join(MONTHS) +r')\s+(\d{4})$',re.I)
AMOUNT = re.compile(r'^(?:(?:EUR|USD|GBP|CHF|€|\$|£)\s*)?[-+−]?\s*(?:\d{1,3}(?:[. ,]\d{3})+|\d+)[,.]\d{2}(?:\s*[-+−])?(?:\s*(?:EUR|USD|GBP|CHF|€|\$|£))?$',re.I)
CURRENCY_NUMBER = re.compile(r'^(?:EUR|USD|GBP|CHF|€|\$|£)\s*[-+]?\d[\d., ]*$',re.I)
PAGINATION = re.compile(r'^(?:(?:pagina|page|blad)\s*)?\d{1,3}\s*(?:van|of|/)\s*\d{1,3}$|^(?:pagina|page|blad)\s+\d{1,3}$',re.I)
STREET = re.compile(r'\b[\w\- ]+(?:straat|laan|weg|plein|gracht|dreef|singel|kade|hof|park)\s+\d+\s*[A-Z]?(?:[-/]\d+)?\b',re.I)
LABELS = {
'datum','date','omschrijving','description','bedrag','amount','saldo','balance','beginsaldo','eindsaldo',
'begin saldo','eind saldo','saldo vorige afschrift','saldo nieuw afschrift','vorig saldo','nieuw saldo',
'rekeninghouder','rekening','rekeningnummer','account','account number','iban','bic','swift','swift/bic',
'af','bij','debet','credit','debit','af (debet)','bij (credit)','totaal af','totaal bij','totaal','total',
'valutadatum','boekdatum','booking date','value date','betaalrekening','spaarrekening','rekeningafschrift',
'afschrift','afschriftnummer','volgnummer','pagina','page','blad','rente','interest','kosten','fees',
'naam','name','adres','address','woonplaats','postcode','telefoon','telephone','kenmerk','referentie',
'betalingskenmerk','mededelingen','naam / omschrijving','naam/omschrijving','omschrijving / mededeling',
'code','soort','type','munt','valuta','currency','eur','usd','gbp','chf','€','$','£','aantal','quantity',
'koers','price','waarde','value','dividend','rendement','return','periode','period','van','tot','t/m',
'overzicht','jaaroverzicht','termijn','aanvullende informatie','uw rekening','uw gegevens',
'boekingsdatum','mededeling','totaalbedrag','af/bij','naam/omschrijving/mededeling',
'naam / omschrijving / mededeling','tegenrekening','transactiedatum','aandelen','effecten',
'saldo na boeking','saldo voor boeking','dagafschrift','bij- en afschrijvingen','opname',
'storting','mutaties','balans','btw','bedrag af','bedrag bij','internetbankieren','nummer',
'overboeking','overschrijving','incasso','betaalautomaat','ideal','sepa','sepa incasso','sepa overboeking',
'bijschrijving','afschrijving','betaling','ontvangst','beleggingsrekening','effectenrekening',
}
SENSITIVE = {'naam':'identity.name','name':'identity.name','rekeninghouder':'identity.name',
             'adres':'identity.address','address':'identity.address','woonplaats':'identity.city',
             'postcode':'identity.city','telefoon':'identity.phone','telephone':'identity.phone',
             'kenmerk':'identity.reference','referentie':'identity.reference','betalingskenmerk':'identity.reference',
             'rekeningnummer':'identity.account','account number':'identity.account'}
DESC = {'omschrijving','description','naam / omschrijving','naam/omschrijving','omschrijving / mededeling','mededelingen','naam/omschrijving/mededeling','naam / omschrijving / mededeling'}
BALANCES = {'beginsaldo':'account.opening','begin saldo':'account.opening','vorig saldo':'account.opening',
            'saldo vorige afschrift':'account.opening','eindsaldo':'account.closing','eind saldo':'account.closing',
            'nieuw saldo':'account.closing','saldo nieuw afschrift':'account.closing',
            'totaal af':'account.debits','totaal bij':'account.credits'}


def normal(text):
    return re.sub(r'\s+',' ',text.casefold().strip(' :\t'))


def is_date(text):
    text=text.strip()
    try:
        if LONG_DATE.fullmatch(text):
            d,m,y=LONG_DATE.fullmatch(text).groups();datetime(int(y),MONTHS.index(m.casefold())+1,int(d));return True
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):
            datetime.strptime(text,'%Y-%m-%d');return True
        if DATE.fullmatch(text):
            parts=re.split(r'[-/.]',text)
            year=int(parts[2]) if len(parts)==3 else 2024
            if year<100:year+=2000
            datetime(year,int(parts[1]),int(parts[0]));return True
    except ValueError:pass
    return False


def is_amount(text):
    return bool(AMOUNT.fullmatch(text.strip()) or CURRENCY_NUMBER.fullmatch(text.strip()))


def suggest(document, values):
    rows=draft_rows(document); by_id={f.id:f for f in document.fragments}
    values.update({'identity.phone':'+31 00 000 0000','identity.email':'persoon@example.invalid',
                   'identity.bic':'TESTNL00XXX','identity.description':'SYNTHETISCHE TRANSACTIE'})
    aliases={};index=0
    # Geometry, never institution names: labelled values and description columns.
    context={};description=set()
    for f in document.fragments:
        n=normal(f.text)
        if n in SENSITIVE or n in BALANCES:
            right=[g for g in document.fragments if g.page==f.page and abs(g.y-f.y)<3 and g.x>f.x+f.ink_width+2]
            if right:
                g=min(right,key=lambda x:x.x)
                if g.x-(f.x+f.ink_width)<180:
                    context[g.id]=SENSITIVE.get(n,BALANCES.get(n))
        if n in DESC:
            others=[g.x for g in document.fragments if g.page==f.page and abs(g.y-f.y)<3 and g.x>f.x+f.ink_width+3]
            end=min(others,default=document.pages[f.page][0]-20)
            for g in document.fragments:
                if g.page==f.page and 45<g.y<f.y-4 and f.x-4<=g.x<end-3:
                    # Footer text/summary labels are not treated as transaction descriptions.
                    if normal(g.text) not in BALANCES and normal(g.text) not in DESC and not PAGINATION.fullmatch(g.text) and not is_date(g.text) and not is_amount(g.text):
                        description.add(g.id)
    # Address blocks imply identity context; keywords inside the block do not override it.
    for f in document.fragments:
        if POSTCODE.search(f.text) and len(f.text)<70:
            for g in document.fragments:
                if g.page==f.page and abs(g.x-f.x)<12 and 0<g.y-f.y<38 and not IBAN.search(g.text) and not is_date(g.text) and not is_amount(g.text):
                    context[g.id]='identity.address' if any(c.isdigit() for c in g.text) else 'identity.name'
    for row in rows:
        text=row['source'].strip(); n=normal(text);f=by_id[row['id']]
        row.update(kind='Unknown text',review_required=True,reason='No generic rule matched')
        def replace(key,kind,reason,review=False):
            row.update(action='replace',replacement=key,kind=kind,review_required=review,reason=reason)
        if row['id'] in context:
            replace(context[row['id']],'Labelled value','Sensitive field context overrides vocabulary');continue
        for label,key in SENSITIVE.items():
            if re.match(r'^'+re.escape(label)+r'\s*:\s*\S',text,re.I):
                alias='field.'+row['id'];values[alias]=text.split(':',1)[0]+': '+values[key]
                replace(alias,'Labelled value','Explicit label and value');break
        if row['action']=='replace':continue
        found=None
        # Whitespace-grouped international IBANs: try longest valid prefix to avoid swallowing a trailing word.
        for match in IBAN.finditer(text):
            candidate=iban.compact(match.group())
            for length in range(min(34,len(candidate)),14,-1):
                if iban.is_valid(candidate[:length]):found=candidate[:length];break
            if found:break
        if found:
            if found not in aliases:
                key=f'auto.account.{len(aliases)+1}';aliases[found]=key;values[key]=f'NL00 TEST {len(aliases):010d}'
            replace(aliases[found],'IBAN','Country format and checksum validated');continue
        if re.search(r'\b[A-Z]{2}\s*\d{2}\s*[A-Z]{4}(?:\s*\d){10}\b',text,re.I):
            replace('identity.account','IBAN-like','Invalid checksum; still replaced',True);continue
        if POSTCODE.search(text):replace('identity.city','Postal address','Dutch postal pattern; no external address lookup');continue
        if STREET.search(text):replace('identity.address','Street address','Generic street suffix and house number');continue
        compact=re.sub(r'^(?:BIC|SWIFT)[ :]+','',text,flags=re.I).strip()
        if n not in LABELS and re.fullmatch(r'[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?',compact) and bic.is_valid(compact):replace('identity.bic','BIC','SWIFT/BIC structure validated');continue
        if re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text):replace('identity.email','Email','Email structure');continue
        phones=list(phonenumbers.PhoneNumberMatcher(text,'NL')) if any(c.isdigit() for c in text) else []
        if any(phonenumbers.is_valid_number(m.number) for m in phones):
            replace('identity.phone','Phone number','libphonenumber numbering-plan validation');continue
        if is_date(text):
            index+=1;key=f'auto.date.{index}'
            base=values.get(f'tx.{(index-1)%max(1,sum(k.endswith(".date") for k in values))+1}.date',values['period.start'])
            values[key]=base
            replace(key,'Date','Calendar-validated date; independently generated replacement');continue
        if is_amount(text):
            index+=1;key=f'auto.amount.{index}'
            number=max(1,sum(k.startswith('tx.') and k.endswith('.amount') for k in values))
            values[key]=values[f'tx.{(index-1)%number+1}.amount']
            replace(key,'Money amount','Decimal/currency pattern; document reconciliation still required');continue
        if row['id'] in description:
            replace('identity.description','Transaction description','Generic description-column geometry');continue
        if PAGINATION.fullmatch(text):
            row.update(action='static',kind='Pagination',review_required=False,reason='Page numbering, not a financial value');continue
        if n in LABELS:
            row.update(action='static',kind='Template label',review_required=False,reason='Exact generic vocabulary match');continue
    return rows


def needs_review(row):return row['action']=='pending' or row.get('review_required',True)
def status(row):
    if needs_review(row):return 'Needs review'
    return {'replace':'Replaced','drop':'Omitted','static':'Kept'}.get(row['action'],'Needs review')
def priority(row):return (0 if row['action']=='pending' else 1 if needs_review(row) else 2,row['page'],row['id'])


def static_allowed(text):
    return bool(PAGINATION.fullmatch(text.strip())) or text.strip() in {'€','$','£'} or not (
        any(c.isdigit() for c in text) or '@' in text or '€' in text)
