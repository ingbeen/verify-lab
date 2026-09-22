"""매매법 이름표와 등급 — 산출물이 어느 폴더에 쌓이는지의 SoT

**등급은 로직이 아니라 분류다.** 검증에서 재 보고 실제로 걸기로 정하면 매매로 승격하고,
접기로 정하면 강등한다. 승격이 성적을 바꾸지 않으므로 **이 파일의 한 줄만 바뀐다.**

[중요] **등급을 호출 측이 넘기면 이 파일이 SoT 가 아니게 된다.** 스크립트가 등급을 박아
넘기던 시절에는 폴더를 손으로 옮겨도 다음 실행이 원래 자리에 다시 만들었다 — 등급을 선언할
자리가 어디에도 없었기 때문이다. 그래서 `report/writer.create_run_directory` 는 등급을
인자로 받지 않고 여기에 묻는다.

**두 축을 함께 둔다.**

- **등급**은 「어디에 쌓이는가」다. 산출물 폴더와 문서 폴더가 이 값이다
- **종류**는 「성적표를 낼 수 있는가」다. 신호가 없는 조사는 거래내역도 성적표도 낼 것이 없다

두 축의 값이 겹치지 않게 고른 것은 의도다. 같은 문자열을 쓰면 **잘못된 축에서 가져와도 값이
나와** 조용히 다른 것을 가리킨다 (`src/verify_lab/CLAUDE.md` 의 `TREND_*` 사례와 같은 이유).
"""

from dataclasses import dataclass
from typing import Final

# ============================================================
# 등급 — 산출물과 문서가 놓이는 자리
# ============================================================

# 재 보는 중인 매매법 후보. **새 매매법이 처음 들어오는 자리**다
GRADE_STUDY: Final = "검증"

# 실제로 걸기로 정한 매매법. 승격은 이 값으로 바꾸는 것뿐이고 성적 계산은 그대로다
GRADE_TRADING: Final = "매매"

# 매매법이 아니라 **데이터·상품의 성질을 재는 것**. 실측 프로브와 채택되지 않은 트랙이 여기 온다
GRADE_SURVEY: Final = "조사"

GRADES: Final = (GRADE_STUDY, GRADE_TRADING, GRADE_SURVEY)

# ============================================================
# 종류 — 성적표를 낼 수 있는가
# ============================================================

# 신호가 있어 거래내역과 성적표를 낸다
KIND_METHOD: Final = "매매법"

# 신호가 없다. 자기 표만 내며 성적표 계약을 요구받지 않는다
KIND_PROPERTY: Final = "성질 조사"

KINDS: Final = (KIND_METHOD, KIND_PROPERTY)


@dataclass(frozen=True)
class Track:
    """매매법·조사 한 줄

    Attributes:
        slug: 코드에서 부르는 이름. 정의처는 `studies/<slug>/constants.py` 의 `TRACK_NAME` 이고
            여기서는 그것을 키로 쓴다
        label: 사람이 부르는 한글 이름. **산출물 폴더 이름과 문서 폴더 이름이 둘 다 이 값**이라
            `docs/<등급>/<label>/` 과 `storage/results/<등급>/<label>/` 의 자리가 그대로 맞는다.
            그래서 **폴더 이름으로 쓸 수 있는 모양이어야** 하며 그 검사는 `report/writer.py` 가 한다 —
            폴더를 `rmtree` 로 비우므로 경로 구분자가 섞이면 산출물 루트 밖을 겨눈다
        grade: `GRADES` 중 하나. 산출물 폴더의 상위 폴더가 이 값이다
        kind: `KINDS` 중 하나
    """

    slug: str
    label: str
    grade: str
    kind: str


# **한 줄이 한 매매법이다.** 승격·강등은 `grade` 를 바꾸는 것뿐이다.
#
# 한글 이름은 `docs/INDEX.md` 이름표와 같아야 하며 `tests/test_tracks.py` 가 대조한다 —
# 두 벌이 되면 한쪽이 낡고, 그때 어느 쪽이 현재인지 판별할 방법이 없다.
#
# [중요] **띄어쓰기 대신 밑줄을 쓴다.** 이 값이 폴더 이름이므로 공백이 들어가면 셸·링크에서
# 매번 따옴표를 달아야 하고, VSCode 확장이 공백 든 경로의 링크를 열지 못한다.
TRACKS: Final = (
    Track("reverse", "역방향", GRADE_TRADING, KIND_METHOD),
    Track("option_expiry", "옵션_만기일", GRADE_TRADING, KIND_METHOD),
    Track("month_end", "월말_진입", GRADE_TRADING, KIND_METHOD),
    # 위 둘을 2×2 로 교차한 검증. **재 보는 중이라 검증 등급**이며, 승격은 결과를 보고
    # 사용자가 정한다
    Track("expiry_monthend", "만기_말일", GRADE_STUDY, KIND_METHOD),
    Track("usdkrw_equivalence", "원달러_ETF_등가성", GRADE_SURVEY, KIND_PROPERTY),
    Track("leverage_tracking", "레버리지_ETF_괴리", GRADE_SURVEY, KIND_PROPERTY),
    Track("futures_leverage", "선물_대_레버리지_ETF", GRADE_SURVEY, KIND_PROPERTY),
    # 매매법으로 설계됐으나 채택되지 않아 실행 코드를 지웠다. 남은 것은 「왜 안 쓰는지의 근거」라
    # 종류도 성질 조사다 — 성적표를 낼 코드가 없으므로 매매법 계약을 요구받으면 안 된다
    Track("usdkrw_grid", "원달러_그리드", GRADE_SURVEY, KIND_PROPERTY),
    # 실측 프로브. 매매법이 아니라 **데이터 소스의 성질**을 잰다
    Track("ecos_probe", "ECOS_실측", GRADE_SURVEY, KIND_PROPERTY),
    Track("pykrx_etf_probe", "pykrx_ETF_실측", GRADE_SURVEY, KIND_PROPERTY),
    Track("pykrx_splice_probe", "pykrx_이어붙이기_실측", GRADE_SURVEY, KIND_PROPERTY),
)

_BY_SLUG: Final = {track.slug: track for track in TRACKS}


def track_of(slug: str) -> Track:
    """slug 로 레지스트리 한 줄을 찾는다.

    Args:
        slug: 매매법 이름. `studies/<slug>/constants.py` 의 `TRACK_NAME` 을 넘긴다

    Returns:
        그 줄

    Raises:
        ValueError: 등록되지 않은 slug 인 경우
    """
    track = _BY_SLUG.get(slug)
    if track is None:
        raise ValueError(f"등록되지 않은 매매법입니다: {slug} (등록처: src/verify_lab/tracks.py)")

    return track


def tracks_of_kind(kind: str) -> tuple[Track, ...]:
    """종류로 걸러 목록을 돌려준다.

    「매매법이면 성적표를 낸다」 같은 계약을 거는 쪽이 쓴다.

    Args:
        kind: `KINDS` 중 하나

    Returns:
        그 종류의 줄들. 레지스트리 순서를 지킨다

    Raises:
        ValueError: 선언되지 않은 종류인 경우
    """
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 종류입니다: {kind} (가능한 값: {list(KINDS)})")

    return tuple(track for track in TRACKS if track.kind == kind)
