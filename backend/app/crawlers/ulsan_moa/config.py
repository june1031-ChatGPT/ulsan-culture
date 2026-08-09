from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UlsanMoaSourceConfig:
    name: str
    base_url: str
    source_type: str
    host_url: str


ULSAN_MOA_SOURCE = UlsanMoaSourceConfig(
    name="울산모아 통합예약",
    base_url="https://ulsan.go.kr/y/yes/",
    source_type="website",
    host_url="https://ulsan.go.kr",
)
