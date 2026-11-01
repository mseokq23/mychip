# 블록 검증 시뮬레이션 (ngspice)

온칩 특성화 IC의 아날로그·혼성 블록이 공식 PDK 모델로 동작하는지 확인하는 스크립트다. 결과 숫자는 칩 설계 계획의 근거로 쓰였고, `run_all.py`가 그 값과 다시 비교한다.

## 준비

공식 PDK 모델(05cmos_model_260210.lib, 05cmos_mosfet_corner.lib)은 킷의 문서 폴더 압축본에서 꺼내 `build/`에만 둔다(저장소에는 넣지 않는다). 문서 폴더가 없으면 한 번 받는다.

```bash
ETRI050_WITH_DOCS=1 bash scripts/setup-etri050.sh        # docs/ETRI_0p5um_NSPL_260820 추가(약 110 MB)
# 또는 모델 두 파일이 있는 폴더를 지정: export ETRI050_PDK_MODELS=/path/to/Model_Parameter
```

킷 표준셀 넷리스트(khu_etri050_stdcells.spice)는 PDK 소자 이름에 맞춰 nfet/pfet → nmos4/pmos4로 바꿔 쓴다.

## 실행

```bash
cd designs/etri050/sim/blocks
python3 run_all.py              # 전부
python3 run_all.py tg pnp       # 일부만
python3 run_all.py post         # 레이아웃 뒤 어레이(designs/etri050/array/build/kelvin_r.json이 있을 때 기본 실행에도 들어감)
```

실행 시간(Codespace 4코어, ngspice-47, 2026-11-01): 전체 약 10분 — RO 384 s(과도 해석 38회), CBCM 128 s(23회), scan 58 s(스캔 6회 + 분주 9회), 나머지는 각각 10 s 이내. 이때 결과는 `BLOCK CHECKS: 23 ok, 0 to check`였다(킷 db09a3d, 111dc09와 문서 PDF 두 개만 다름). CBCM 블록 두 단계가 더해져 cbcm_block 228 s(54회), cbcm_post 373 s(97회)가 늘었고, 두 단계의 15개는 모두 ok였다(같은 날, 같은 환경). 로컬 ngspice-42(2코어)에서도 같은 값이 나온다.

끝에 `BLOCK CHECKS: N ok, M to check`가 나온다. CHECK는 계획 값과 허용 범위 밖이라는 뜻이고(ngspice 판이나 모델 파일이 다를 때 등), 원인을 확인할 대상이다.

| 스크립트 | 확인 내용 | 계획에 쓴 값 |
|---|---|---|
| tg_ron.py | 어레이 스위치 TG의 0.05–4.95 V 최대 Ron | N100/P250: 45 Ω(TT 27 °C), 62 Ω(SS 125 °C) |
| array_path.py | 8×8 NMOS 어레이 경로(PANA 다이오드, 미선택 행·열, Kelvin SMU) 대 이상 소자 | 문턱 이상 전류 오차 ≤ 0.04%, 27 °C ΔVt ≤ 0.012 mV, 125 °C 누설 1.2–5.5 nA, open 채널 차감 후 ΔVt ≤ 0.06 mV |
| array_kelvin.py | 드레인 sense를 열 끝에서 받을 때와 셀마다 받을 때(행 선택 TG) 비교, 먼 행·MET2 열 선로 | 셀 sense: R_tot 오차 ≤ 0.01%. 열 끝 sense: +1.1%(선로 10 µm)·+1.8%(6 µm) |
| array_post.py | 레이아웃 뒤: array_path 하네스에 셀 sense TG, 그린 스위치 크기, 그린 어레이에서 뽑은 Kelvin 루프 안 저항(`designs/etri050/array/kelvin_r.py`) | W/L 9/0.6 R_tot +0.16 %(typ)·+0.24 %(최대), typ 표를 빼면 ≤ 0.08 %, 다른 셀 ≤ 0.03 %. ΔVt 27 °C ≤ 0.004 mV, 125 °C open 뺀 뒤 ≤ 0.047 mV |
| cbcm.py | CBCM 정확도·주파수·PADR 영향·125 °C·C–V | 300 fF +1.2%, 1 pF +0.3%, PADR 영향 ≤ 0.3%p |
| cbcm_block.py | 그린 CBCM 블록의 회로 넷리스트(`designs/etri050/gen/etri050_cbcm.py`): 비중첩 생성기, 셀마다 PMOS 게이트 NAND2X1, 공통 NMOS 게이트, 10개 셀과 구조 모델(PIP·N+는 PDK 모델, 금속은 규칙 문서 값). 5코너·125 °C·VDD 4.5/5.5 V·0.2/1/5 MHz | 300 fF 셀 +1.49 %, 게이트 +0.2 %, 빈 셀 0.00 fF, 비중첩 ≥ 0.30 ns(FF, 4.5 V), 미선택 셀 영향 0.002 %, PADR +0.24 %p, C–V(1.5–5 V) ≤ 0.51 % |
| cbcm_post.py | 레이아웃 뒤 CBCM: cbcm_block의 넷리스트에 그린 블록의 배선 용량(`designs/etri050/cbcm/cbcm_c.py`, 규칙 문서 용량표)과 그린 기하의 구조 모델(PIP pipcap_i, N+ ndiode, 게이트 nmos4)을 넣는다. N+ 셀은 ndiode와 nmos4 소스·드레인 접합 값을 함께 낸다 | 빈 셀 0.00 fF, 셀 2 +4.50 fF(+1.47 %, 코너·VDD·클록에 따라 +1.34–1.68 %), 게이트 +0.2 %, 비중첩 ≥ 0.47 ns, PADR +0.25 %p, C–V(셀 6–9, 1.5–5 V) ≤ 0.96 % |
| ro_bank.py | 31단 RO 6종 × 5코너(27 °C) + TT 125 °C, INV RO의 VDD 4.5–5.5 V | INV 123.1, NAND 93.8, NOR 66.8, FO4 52.8, 배선 65.0, 저항 69.1 MHz(TT 27 °C) |
| scan_divider.py | 8비트 스캔 + 섀도 + 3→8 디코더(3 PVT × 1·10 MHz), 분주기 ÷16(100–200 MHz) | 모두 정상 |
| pnp_thermo.py | pnp10 온도계(PADR 경유) 3전류법 대 2전류법 | 3전류법 오차 ≤ +0.16 K(27–125 °C), 2전류법 −4.9 K(125 °C) |
| lsplit.py | W 9 µm 포화 전류, Terada–Muta(L 0.6·1.2·3·9 µm) | 4.56 mA, R_sd 121 Ω(27 °C)·135 Ω(125 °C) |

PANA ESD 다이오드는 킷 GPIO GDS(ETRI_NSPL_GPIO_250610)에서 읽은 크기(극성마다 10 × 10 µm 12개, 면적 1200 µm²·둘레 480 µm)로 넣었다. 배선 저항·기생 용량은 추정값이므로 레이아웃 추출 뒤 다시 돌린다. 어레이는 `array_post.py`로 다시 돌렸다: 계획 하네스의 소스 판은 sense 탭에 전류가 흐르지 않아 이상적이었고, 그린 어레이의 소스 비아·판(셀마다 0.42–0.68 Ω, typ)이 W/L 9/0.6 셀에서 +0.16 %로 드러난다(`designs/etri050/array/README.md`).
