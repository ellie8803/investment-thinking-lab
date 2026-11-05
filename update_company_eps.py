#!/usr/bin/env python3
"""Collect selected SEC GAAP diluted EPS facts, with conservative quarter extraction."""
import datetime as dt
import json
import os
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TICKERS = ['AAPL','MSFT','GOOGL','GOOG','AMZN','META','NVDA','AVGO','TSLA','AMD','NFLX','ORCL','CRM','INTC','MU','PLTR']
CONTACT = os.environ.get('SEC_CONTACT_EMAIL','').strip()
if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', CONTACT):
    raise SystemExit('Set repository variable SEC_CONTACT_EMAIL to your valid contact email first.')
UA = f'InvestmentThinkingLab/7.3 contact {CONTACT}'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

def date(s):
    return dt.date.fromisoformat(s)

def collect(facts):
    us=facts.get('facts',{}).get('us-gaap',{}).get('EarningsPerShareDiluted',{})
    units=us.get('units',{}).get('USD/shares',[])
    annual,quarter={},{}
    for f in units:
        if not all(k in f for k in ('start','end','filed','val','form','fy','fp')): continue
        if f['form'] not in ('10-K','10-Q'): continue
        try:
            start,end,filing=date(f['start']),date(f['end']),date(f['filed'])
            days=(end-start).days+1
            val=float(f['val'])
            fy=int(f['fy'])
        except (ValueError,TypeError,OverflowError):continue
        if not (-10000<val<10000):continue
        # SEC FY and FP are not always the measured fiscal quarter for comparative facts.
        # Only use frames for exact annual and quarterly period identity.
        frame=f.get('frame','')
        if f['form']=='10-K' and 300<=days<=380 and re.fullmatch(r'CY\d{4}',frame):
            year=int(frame[2:]);key=year
            candidate={'year':year,'eps':val,'start':str(start),'end':str(end),'filed':str(filing),'accession':f.get('accn','')}
            if key not in annual or candidate['filed']>annual[key]['filed']:annual[key]=candidate
        elif f['form']=='10-Q' and 65<=days<=105 and re.fullmatch(r'CY\d{4}Q[1-3]',frame):
            year=int(frame[2:6]);q=int(frame[-1]);key=(year,q)
            candidate={'year':year,'quarter':q,'eps':val,'start':str(start),'end':str(end),'filed':str(filing),'accession':f.get('accn','')}
            if key not in quarter or candidate['filed']>quarter[key]['filed']:quarter[key]=candidate
    # Do not derive Q4 by subtracting diluted EPS; annual/quarter weighted shares differ.
    return sorted(annual.values(),key=lambda x:x['year'])[-10:],sorted(quarter.values(),key=lambda x:(x['year'],x['quarter']))[-32:]

def main():
    mapping=get('https://www.sec.gov/files/company_tickers.json')
    by_ticker={str(v['ticker']).upper():v for v in mapping.values()}
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    output={'schema_version':1,'updated_at':now,'source':'SEC EDGAR companyfacts (GAAP diluted EPS, USD/shares)','companies':{}}
    good=0
    for ticker in TICKERS:
        try:
            meta=by_ticker[ticker]
            cik=str(meta['cik_str']).zfill(10)
            facts=get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
            annual,quarter=collect(facts)
            if not annual and not quarter:raise ValueError('No framed diluted EPS observations')
            filings=[x['filed'] for x in annual+quarter]
            output['companies'][ticker]={'name':meta['title'],'cik':cik,'annual':annual,'quarterly':quarter,'latest_filed':max(filings,default=None)}
            good+=1
        except Exception as exc:
            output['companies'][ticker]={'error':str(exc)[:180]}
        time.sleep(0.3)
    if good<8:raise SystemExit(f'Only {good}/{len(TICKERS)} companies succeeded; keep previous company-eps.json')
    dest=ROOT/'company-eps.json';tmp=ROOT/'company-eps.json.tmp'
    tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(dest)
    print('Wrote',dest,'successful',good,'of',len(TICKERS))

if __name__=='__main__':main()
