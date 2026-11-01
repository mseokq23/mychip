# 직결 기준 소자

어레이·스위치를 거치지 않고 패드에 바로 잇는 기준 소자다. 생성기는 `designs/etri050/gen/etri050_direct.py`이고, `etri050_mos.py`처럼 Python이 λ 격자(0.3 µm, 반 λ 허용)에서 좌표를 정하면 Magic이 킷 기술로 그린다. 셀마다 LVS용 회로도 넷리스트를 같이 쓴다.

```bash
python3 designs/etri050/gen/etri050_direct.py            # lsplit, mosc → designs/etri050/direct/build
python3 designs/etri050/gen/etri050_direct.py --check    # Magic DRC, ETRI GDS, 공식 규칙 KLayout DRC, LVS (etri-check)
```

| 셀 | 내용 | 크기 | 포트 |
|---|---|---|---|
| `lsplit` | NMOS W 9 µm, L 0.6·1.2 µm(어레이 열 0·1과 같은 기하), 게이트·소스 공유 | 13.8 × 27.0 µm | LG, LD1F, LSF, LD2F, VSS |
| `mosc` | N-well MOS 커패시터: P채널 게이트 99.9 × 99.9 µm 4개(2 × 2, 합 39,920 µm², 약 118 pF), 양옆 p+ 줄이 반전층 공급, 조각 사이 n+ 웰 탭 | 223.2 × 221.1 µm | CHI(게이트), CLO(N-well + p+) |

<img src="../../../docs/img/lsplit_layout.png" alt="lsplit 레이아웃" height="320"> <img src="../../../docs/img/mosc_layout.png" alt="mosc 레이아웃" height="320">

- `lsplit`: 드레인 두 개와 공유 소스의 접촉 줄마다 위쪽 끝은 force(비아1 → 금속2), 아래쪽 끝은 sense(비아1 → 금속2)로 나눈다(접촉 줄에서 갈라지는 Kelvin). 게이트는 활성 영역 위 poly 막대로 묶어 왼쪽 접촉에서 금속1로 낸다. 기판 탭은 sense 비아 아래에 두고 금속2가 그 위를 지난다. sense 줄은 force와 같은 넷이라 셀 포트로는 내지 않는다(한 넷의 두 포트는 LVS가 구분하지 못함). 칩 조립 때 sense 패드(LD1S, LSS, LD2S)로 잇는다.
- `mosc`: 게이트 한 점에서 가장 가까운 n+ 탭까지 약 54 µm로, 탭 거리 규칙(≤ 60 µm) 안이다. 게이트 접촉 줄은 조각마다 위아래에 있고 열마다 금속1 띠로 묶어 위쪽 막대(CHI)로, p+ 줄과 탭은 아래쪽 막대(CLO)로 모은다. Magic 추출은 소스·드레인이 같은 넷이라 "device missing 1 terminal; connecting remainder to node CLO" 경고를 4번 내며, 결과 넷리스트(pfet D = S = B = CLO, G = CHI, W = L = 99.9 µm)는 의도와 같다.
- 99.9 µm는 λ 격자(333λ)에 맞춘 값이다(100 µm는 격자 밖).

## 결과 (2026-11-01, Codespace, 킷 db09a3d)

| 셀 | Magic DRC | 공식 규칙 KLayout DRC | LVS |
|---|---|---|---|
| lsplit | 0 | 0 | MATCH (nfet 9/0.6, 9/1.2, 속성 일치) |
| mosc | 0 | 0 | MATCH (pfet 99.9/99.9 × 4, 속성 일치) |

## PNP 온도계와 히터

Magic 추출은 BJT·poly2 저항을 소자로 만들지 못하고, 킷의 Magic ETRI 출력 스타일은 BJT(56)·RES(51)·LVSD(60) 표시층을 만들지 않는다. 그래서 이 둘은 ETRI 층 번호로 된 GDS 셀로 만들어 칩 GDS 단계에서 합친다(패드 링과 같은 ETRI-G 경로). 칩 LVS에서는 GPIO처럼 핀만 있는 블랙박스로 다룬다.

```bash
bash designs/etri050/direct/run_pdk_cells.sh   # pdk_cells.py → build/pnp10.gds, build/heater.gds → 공식 규칙 KLayout DRC
```

- `pnp10`: 킷 `analog_ETRI/GDS/NSPL_0p5um.gds`의 PDK 셀을 하위 셀(ntap·ptap)째 그대로 옮긴다. 49 × 49 µm, BJT 표시층 56 포함. 금속1 단자는 이미터(가운데 10 × 10 µm, 19.5–29.5 µm), 베이스(안쪽 고리, 13–36 µm), 콜렉터(바깥 고리, 4.5–44.5 µm)다. 베이스·콜렉터는 VSS, 이미터는 PE1·PE2.
- `heater`: 같은 파일의 PDK `p2res`(W 2 × L 100 µm)와 같은 층 구성으로 W 20 × L 120 µm(6 sq, 약 750 Ω)를 만든다. POLY2(13) 본체, 저항 전체를 덮는 RES(51), 양끝 접촉 사이(L)를 정하는 LVSD(60), 끝마다 금속1 머리(1.8 µm) 아래 접촉(0.6 µm) 16개를 1.2 µm 간격으로 둔다. 접촉은 p2res처럼 LVSD 경계에 붙이고 POLY2 끝에서 0.6 µm, 옆에서 0.7 µm 안쪽이다(규칙 14.PL2PR.E2 ≥ 0.5, 14.PL2PR.S1 ≥ 0.6). 셀 124 × 21.6 µm, 단자 A(왼쪽 머리)·B(오른쪽 머리).

### 결과 (2026-11-01, Codespace, 킷 db09a3d)

| 셀 | 공식 규칙 KLayout DRC |
|---|---|
| pnp10 | 0 |
| heater | 0 |
