# 칩 조립 pdkv

PDK 모델 검증용 온칩 특성화 IC의 최상위 조립이다. 킷의 칩 조립 방식(FIR_PE MPW240925002, pong_pt1 MPW2025 STD-II)과 같게 패드 링(`pdkv_Pad`), 코어(`pdkv_Core`), 코어–패드 배선(`pdkv_Pin_Route`)을 따로 만들어 최상위 `pdkv_Top`으로 합친다.

```
pins.csv          28개 패드: 패드 위치(W1–W7 아래→위, N1–N7 왼→오, E1–E7 아래→위, S1–S7 왼→오), 핀, 셀, 포트, 기능, 범위
pad_ring.py       킷 28핀 GPIO 템플릿 → build/pdkv_Pad.mag, build/pad_pins.json(코어 쪽 포트 위치)
run_pad_ring.sh   패드 링 생성 → Magic GDS(lambda=0.30(ETRI-G)) → 공식 규칙 KLayout DRC, 킷 템플릿 링과 비교
```

## 패드 링

![pdkv 패드 링: 1.9 × 1.9 mm 프레임, 변마다 7개](../../../docs/img/pdkv_pad_ring.png)

- 킷 템플릿 `pads_ETRI/MPW_PAD_28Pin_IO.mag`는 PIC 28개(PAD_0–PAD_27), 모서리 4개, 필러 32개를 1.9 × 1.9 mm 프레임에 135 µm 간격으로 놓는다. `pad_ring.py`는 템플릿 배치를 그대로 두고 셀만 바꾼다(PANA 20, PIC 4, POB4 1, PVDD 2, PVSS 1). 킷의 FIR_PE·pong_pt1도 같은 템플릿에서 셀을 바꿔 만들었다.
- 템플릿 순서는 쓰기 전에 변환 행렬로 확인한다: S1–S7 = PAD_0–PAD_6, E1–E7 = PAD_7–PAD_13, N1–N7 = PAD_20–PAD_14, W1–W7 = PAD_27–PAD_21. 패드 중심은 S변 545, 680, …, 1355 µm다.
- 코어 쪽 포트는 GPIO 셀 안쪽 끝(다이 좌표 442 µm와 1458 µm)의 금속2다. 코어 창은 1016 × 1016 µm다. 포트 위치는 `build/pad_pins.json`에 남긴다(PANA는 PAD 47.2 µm·PADR 27.2 µm 폭, PIC Y·POB4 A는 3.2 µm 폭).
- force·히터 6핀(ADF, ASF, LD1F, LSF, LD2F, HT)은 PANA의 무저항 포트 PAD에 잇는다. ETRI가 허용하지 않으면 `--force-port PADR`로 직렬 저항 포트로 바꾼다(문의 1번 답 대기).

### 결과 (2026-11-01, Codespace, 킷 db09a3d)

| 항목 | pdkv_Pad | 킷 템플릿 링(PIC 28개) |
|---|---|---|
| 셀 | 64개(PANA 20, PIC 4, POB4 1, PVDD 2, PVSS 1, 모서리 4, 필러 32), 못 찾은 셀 0 | 64개 |
| 크기 | 1705 × 1705 µm(97.5–1802.5 µm) | 같음 |
| 공식 규칙 KLayout DRC | 14개, 모두 5.NSD.S1 | 84개, 모두 5.NSD.S1 |

- 5.NSD.S1 표시는 ETRI GPIO 셀 안에서 나온다: GPIO 셀만 있는 템플릿 링에도 같은 규칙이 84개(PIC마다 3개) 있고, 디지털 입출력 셀이 5개(PIC 4·POB4 1)뿐인 우리 링은 14개다. 킷의 FIR_PE Calibre 결과에도 5.NSD.S1이 66개 있다.

## 다음 단계

코어(제어 블록 + 직결 소자 + 이후 어레이·CBCM·RO), 코어–패드 배선, 그리고 킷 `generate_chip.sh` 순서의 GDS 조립을 한다. 패드는 ETRI-G 스타일로, 코어와 배선은 ETRI 스타일로 쓴 뒤 합치며, 코어 GDS는 `scripts/fill_notches.py`로 금속 홈을 메운다.
