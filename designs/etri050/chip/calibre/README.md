# Calibre로 직접 확인하기

ETRI는 제출 GDS를 Calibre로 검사한다. 킷에 있는 pong_pt1(MPW2025 STD-II, 제작·측정된 칩)의 ETRI Calibre DRC 요약·결과가 그 근거다(`Projects/RTL/pong_pt1/.../DRC_0`, 2025-06-15, Calibre v2019.4_36.18). 우리 검사는 KLayout으로 한다: 킷 덱, `scripts/metal_rules.py`, `scripts/calibre_rules.py`. 이 폴더는 Calibre가 있는 컴퓨터(학교·IDEC 서버 등)에서 ETRI와 같은 덱·같은 설정으로 칩을 돌리는 묶음을 만든다. 결과를 우리 예측과 맞춰 보는 스크립트도 함께 넣는다.

## 만들기

```
ETRI050_DK=<킷> python3 designs/etri050/chip/calibre/make_run.py      # 약 70 s
```

`run_chip.sh`가 만든 `build/pdkv_Top.gds`를 쓴다. 결과는 `build/calibre/` 폴더와 그 압축 파일 `build/pdkv_calibre.tar.gz`(약 4.8 MB)다. 덱은 킷의 PDK 압축 파일(`docs/ETRI_0p5um_NSPL_260820/NSPL_05CMOS_PDK_260820.tar.gz`의 `Calibre/DRC`·`ANT`·`LVS`)에서 꺼내 묶음에만 넣고, 저장소에는 넣지 않는다.

| 파일 | 내용 |
|---|---|
| `NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_{DRC,ANT,LVS}.cal` | ETRI 덱, 바꾸지 않음 |
| `pong_pt1_Top_Pad.gds`, `pong_pt1_Pad.drc.summary.etri` | ETRI가 검사한 칩과 그 요약(설정 확인용) |
| `pdkv_Top.gds` | 우리 칩(실링·칩 경계 포함) |
| `pdkv_Top_noseal.gds` | 실링·칩 경계를 뺀 판. `PDKV_SEAL=0`으로 조립한 것과 층마다 XOR 0이고, 범위는 선례와 같은 97.5–1802.5 µm |
| `pdkv_Core.gds`, `pdkv_Core.cdl` | 코어 LVS 입력(`lvs_inputs.py`, 아래) |
| `drc_pong.cal` | 1. pong_pt1을 ETRI 설정으로. 개수가 ETRI 요약과 같아야 한다 |
| `drc_pdkv_Top.cal`, `drc_pdkv_Top_noseal.cal` | 2. 우리 칩, 같은 설정 |
| `ant_pdkv_Top.cal` | 3. 안테나 덱. PDK의 `runant.com`은 헤더 없이 덱을 넘기는데, 덱의 LAYOUT 줄은 주석이라 그대로는 돌지 않는다 |
| `lvs_pdkv_Core.cal` | 4. 코어 LVS. PDK `lvs_header.cal`에 우리 파일 이름과 `VIRTUAL CONNECT NAME "VDD"`만 넣었다 |
| `run_calibre.sh` | 1–4를 차례로 돌리고 `compare.py`까지 부른다 |
| `compare.py`, `expected.json` | 결과를 읽어 예측과 맞춘다(Python 3만 필요, KLayout 없음) |

DRC 헤더 설정은 ETRI의 pong 요약에 적힌 것과 같다: 검사마다 결과 1000개까지(`DRC MAXIMUM RESULTS 1000`), 결과마다 꼭짓점 4096개까지, 결과는 셀 좌표에 배치 변환을 붙여(`DRC CELL NAME YES CELL SPACE XFORM`), 요약은 셀별로(`REPLACE HIER`). 덱 자체는 PRECISION 1000·RESOLUTION 10·TEXT DEPTH PRIMARY다.

## Calibre 컴퓨터에서

```
tar xzf pdkv_calibre.tar.gz && cd pdkv_calibre
bash run_calibre.sh                         # 몇 분. 여러 CPU를 쓰려면 CALIBRE_OPTS="-turbo 4"
```

하나씩 돌리려면 설계 가이드(03_..._Design Guide V1.1, 8–9장)의 명령 그대로다.

```
calibre -drc -hier drc_pong.cal             # 1
calibre -drc -hier drc_pdkv_Top.cal         # 2a  (2b: drc_pdkv_Top_noseal.cal)
calibre -drc -hier ant_pdkv_Top.cal         # 3
calibre -lvs -hier lvs_pdkv_Core.cal        # 4
python3 compare.py .
```

결과는 `calibre -rve -drc pdkv_Top.drc.results`(LVS는 `calibre -rve -lvs svdb`)로 본다. 또는 결과 파일(`*.drc.results`, Calibre ASCII)을 KLayout 마커 브라우저로 GDS 위에 연다.

## 판정 (`compare.py`)

1. **pong_pt1**: 검사 209개마다 결과 개수가 같아야 하고(합계 1338), 층마다 원래 도형 수도 ETRI 요약과 같아야 한다. 같으면 이 Calibre와 설정이 ETRI 실행처럼 GDS를 읽고 검사한다는 뜻이다. 다르면 2–4를 믿기 전에 버전과 설정부터 본다.
2. **pdkv_Top**: 결과마다 위치로 나눈다.
   - 패드 셀: ETRI GPIO 셀 안(라이브러리와 층마다 같은 셀). 예측은 10.MET2.S2 10곳 안팎과 11.VIA2.S1 8곳 안팎(셀 안 비아2 간격 0.65 µm, KLayout은 16쌍)이다. ETRI의 pong 실행에서도 패드 셀에 같은 두 검사가 나왔다(30·8).
   - 실링: 바깥 30 µm. 7.CONT.W·9.VIA1.W·11.VIA2.W(접촉·비아 줄이 링 모양이라. 덱 이력에 "DRC Error Waive : Sealing Region")와 2.ACT.E5 4개, 6.PSD.E 2개. `pdkv_Top_noseal`에는 없어야 한다.
   - 알려진 것: 1.PWL.bad2 2개(CBCM n+ 접합 셀 6·7, 추가 문의 3).
   - **UNEXPECTED**: 그 밖의 모든 것. 우리 검사가 놓친 것이므로 좌표를 보고 고친다.
3. **안테나**: 0개 예측. 규칙 문서의 안테나 검사(`scripts/antenna_rules.py`)는 깨끗하다. Calibre 덱은 식이 다르다(금속 둘레 × 두께, 접촉·비아 면적 비, 확산 0.202 µm² 이상을 다이오드로 침). 그래서 이것이 그 식의 첫 실제 검사다.
4. **LVS**: `CORRECT` 예측. 아니면 보고서의 불일치 줄을 본다.

## 코어 LVS 입력(`lvs_inputs.py`)

패드 링은 ETRI 셀이라 넷리스트가 없다. 선례(FIR_PE)의 설계 DB 접수서도 LVS 리포트를 "코어 부분에 한함"으로 받았다. 그래서 `chip_lvs.py`와 같은 범위인 패드 링 안쪽을 비교한다.

- `pdkv_Core.gds`: `pdkv_Top`에서 패드 링과 실링(칩 경계 포함)을 빼고 최상위 셀 이름을 `pdkv_Core`로 바꾼다. 패드 셀의 코어 포트 28개(금속2 사각형)를 패드 셀에 있는 그대로 금속2로 그린다. 그래서 포트에서 만나는 선은 여기서도 만난다(PVSS 포트의 VSS 세 갈래). 각 포트 가운데에는 최상위 MET2TXT(44) 라벨을 칩 넷 이름으로 둔다. PVDD → VDD, PVSS → VSS, force·sense 쌍 → 그 노드(ASF/ASS → SRC, LD1F/LD1S → D1, LSF/LSS → S, LD2F/LD2S → D2), 나머지는 핀 이름이다. 라벨은 23종 28개다. 두 PVDD 포트는 코어 안에서 서로 다른 VDD 넷(W1: 제어 블록·어레이·RO, S7: CBCM)에 닿고, 실제 칩에서는 패드 링 VDD 레일이 둘을 잇는다. 그래서 헤더가 이름으로 잇는다.
- `pdkv_Core.cdl`: `chip_lvs.py`의 기준 넷리스트(블록 회로도, 고정한 제어 넷리스트, 칩 연결)를 `.SUBCKT pdkv_Core` 하나로 편 것이다. 포트 23개, 소자는 nmos4 1504, pmos4 1567, p2res 31, pipcap 1, pnpbjt 2다. 소자 줄은 설계 가이드 3.3–3.8의 PDK CDL 출력 형식이다: `M d g s b nmos4 W= L= m=1`, `R a b $[p2res] w= l=`, `C a b $[pipcap] w= l=`, `Q c b e pnpbjt m=1 area=`(m²). 덱은 W·L(MOS, P2RES, PIPCAP)과 A(PNP)를 그대로(허용 0) 비교한다.
- 스스로 확인: CDL을 다시 읽으면 기준 소자와 하나하나 같다(종류, 단자 넷, 비교하는 값; 인스턴스 이름 중복 없음). 라벨마다 `chip_lvs.py` 추출(일치)에서 그 이름의 넷 위에 있다.

## 검증한 것

- `compare.py`의 결과 파일 읽기: ETRI의 pong 결과 파일(셀 좌표 + 배치 변환)에서 검사 12개의 개수가 요약과 모두 같고, 좌표는 칩 좌표로 바뀐다(예: 8.MET1.S2 (499.5, 551.264)–(500.4, 553.936)).
- 판정: 우리 예측으로 만든 가짜 결과(실링 링, 2.ACT.E5·6.PSD.E 띠, CBCM 셀 좌표의 1.PWL.bad2, 패드 셀 결과)에 예전 넓은 금속 자리(8.MET1.S2)를 하나 심으면, 그 하나만 UNEXPECTED가 되고 종료 코드는 1이다. 빼면 0이다. ETRI 요약을 우리 실행인 것처럼 넣으면 pong이 "same as ETRI's run"이다.
- 이 묶음을 만들다 찾은 것: 킷 KLayout 덱의 넓은 금속 간격 검사(8.MET1.S2·10.MET2.S2·12.MET3.S2)는 아무것도 내지 않는다. 넓은 금속이 금속의 일부라 KLayout 기본값인 shielding이 모든 쌍을 가린다. `scripts/metal_rules.py`도 같은 식이었다. shielding을 끄자 pong에서 ETRI Calibre 결과 자리(8.MET1.S2 49개 중 48, 10.MET2.S2 30개 모두)가 나왔다. 우리 칩에서는 CBCM 아래 34곳이 걸렸다(칩 README 참고, 고침).
