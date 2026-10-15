"""Static read-only reference/evidence endpoints, no operator commands."""
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from core.v14_evidence_gates import inventory

BIBLIOGRAPHY = [
 ('GES','De Soto et al. (2006)','https://doi.org/10.1016/j.solener.2005.06.010','Five-parameter photovoltaic IV model'),
 ('GES','pvlib SDM documentation','https://pvlib-python.readthedocs.io/en/latest/reference/pv_modeling/sdm.html','Explicit model parameters and IV prediction'),
 ('GES','PVPMC Sandia','https://pvpmc.sandia.gov/','Transparent performance-model benchmarking'),
 ('HES','IEC 60041:1991','https://webstore.iec.ch/en/publication/154','Hydraulic turbine field-acceptance methods'),
 ('HES','Bergant (2025), Water Hammer in Francis-Turbine Schemes','https://www.mdpi.com/1996-1073/18/24/6404','Hydraulic transient risks; Francis scope'),
 ('RES','OpenFAST documentation','https://openfast.readthedocs.io/','Coupled aero-servo-elastic simulation'),
 ('RES','ROSCO documentation','https://rosco.readthedocs.io/en/latest/','Reference wind turbine controllers'),
 ('RES','IEC 61400-12-1:2022','https://webstore.iec.ch/en/publication/68499','Wind power curve measurement'),
 ('RES','Saint-Drenan et al. (2019)','https://arxiv.org/abs/1909.13780','Environment-sensitive parametric power curves'),
 ('OT','NIST SP 800-82 r3','https://csrc.nist.gov/pubs/sp/800/82/r3/final','Operational technology cybersecurity'),
 ('OT','ISA/IEC 62443','https://www.isa.org/standards-and-publications/isa-standards/isa-iec-62443-series-of-standards','IACS security program'),
 ('OT','IEC 61850-5','https://webstore.iec.ch/en/publication/6012','Utility automation communication requirements'),
 ('OT','IEC 62351 series','https://webstore.iec.ch/en/publication/6912','Utility communications security'),
]

HTML = '''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V1.4 Bilimsel Kanıt Merkezi</title>
<style>body{background:#0d1725;color:#f0f6ff;font:16px system-ui;margin:0}main{max-width:1050px;margin:auto;padding:30px}a{color:#92d8ff}article{padding:20px;margin:14px 0;background:#1b2e42;border-radius:12px;border:1px solid #355571}small{color:#c5d5e5}h1{font-size:26px}</style>
<main><small>SIMULATION / SHADOW • SALT OKUNUR</small><h1>Literatür ve Saha Kanıt Merkezi v1.4</h1><p>Bu sistem araştırma modelleri sunar; gerçek üretici veya tesis sertifikasyonu değildir.</p>
<article><h2>Bilimsel Kaynaklar</h2><p><a href="/api/v1/research/v14/sources">Kaynak listesi (JSON)</a></p></article>
<article><h2>Saha Kabul Kanıtları</h2><p><a href="/api/v1/research/v14/gates">Kanıt gereksinimleri (JSON)</a></p><p>Belgelerin bulunması bağımsız inceleme yerine geçmez.</p></article>
<article><h2>Model karşılaştırması</h2><p>Offline CSV doğrulama için <code>python -m tools.v14_validate_csv</code> aracını kullanın. Sadece geçmiş gözlemler değerlendirilir; üretim tesisi kontrol edilmez.</p></article>
<p><a href="/platform/dashboard">← Platform paneli</a></p></main>'''


def create_v14_router():
    r=APIRouter(tags=['v1.4 Research evidence — read only'])
    @r.get('/api/v1/research/v14/sources')
    def sources():
        return {'research_only':True,'references':[{'area':a,'title':b,'url':c,'use':d} for a,b,c,d in BIBLIOGRAPHY]}
    @r.get('/api/v1/research/v14/gates')
    def gates():
        # Never serve local evidence paths or raw documents over HTTP.
        return inventory(None)
    @r.get('/platform/research',response_class=HTMLResponse)
    def page():return HTMLResponse(HTML)
    return r
