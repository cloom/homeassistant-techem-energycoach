"""API Client for Techem EnergyCoach portal (energycoach.techem.be).

Uses lightweight HTTP session requests to navigate WebDev 26 forms
and extract XML-encoded table datasets without headless browser overhead.
"""

from __future__ import annotations

import re
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://energycoach.techem.be"
LOGIN_URL = f"{BASE_URL}/WEBENERGY_OCCUPANTS/"


class TechemError(Exception):
    """Base exception for Techem EnergyCoach."""


class TechemAuthError(TechemError):
    """Authentication failed."""


class TechemConnectionError(TechemError):
    """Network connection failed."""


class TechemParseError(TechemError):
    """Failed to parse portal response."""


@dataclass
class MeterReading:
    """Represents a meter and its consumption data."""

    meter_id: str
    meter_type: str  # eau_chaude, eau_froide, chauffage
    location: str
    current_month: str
    current_value_raw: float  # hL for water, units for heat
    current_value_m3_or_units: float  # converted m3 for water, units for heat
    exercise_total_raw: float
    exercise_total_m3_or_units: float
    monthly_consumption: dict[str, float] = field(default_factory=dict)
    bimonthly_consumption: dict[str, float] = field(default_factory=dict)
    building_average: dict[str, float] = field(default_factory=dict)



@dataclass
class TechemData:
    """Represents all data fetched from Techem EnergyCoach."""

    building_info: str
    meters: dict[str, MeterReading] = field(default_factory=dict)
    annual_history: list[dict[str, Any]] = field(default_factory=list)


class TechemEnergyCoachClient:
    """Client for Techem EnergyCoach occupant portal."""

    def __init__(self, username: str, password: str, timeout: int = 25) -> None:
        """Initialize client."""
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self._post_action: str | None = None

    def login(self) -> str:
        """Authenticate against Techem portal and return post-login HTML."""
        try:
            # 1. GET landing page to obtain the dynamic session action URL
            r1 = self.session.get(LOGIN_URL, timeout=self.timeout)
            if r1.status_code != 200:
                raise TechemConnectionError(
                    f"Failed to load login page: HTTP {r1.status_code}"
                )

            soup1 = BeautifulSoup(r1.text, "html.parser")
            form1 = soup1.find("form")
            if not form1 or not form1.get("action"):
                raise TechemParseError("Login form not found")

            action1 = form1.get("action")
            post_url = BASE_URL + action1 if action1.startswith("/") else action1

            # 2. POST credentials
            login_data = {
                "WD_JSON_PROPRIETE_": '{"m_oProprietesSecurisees":{}}',
                "WD_BUTTON_CLICK_": "A14",
                "WD_ACTION_": "",
                "A34": "1",  # Language: 1 = Belgique - FR
                "A8": self.username,
                "A10": self.password,
                "A28": "1",  # Accept terms checkbox
                "A54": "_NN:Mozilla/5.0 _NO: 1 _NP: 1 _NT: 1 _NV: 124",
            }

            r2 = self.session.post(post_url, data=login_data, timeout=self.timeout)
            if r2.status_code != 200:
                raise TechemConnectionError(
                    f"Login submission failed: HTTP {r2.status_code}"
                )

            if "invalide" in r2.text.lower() and "mot de passe" in r2.text.lower():
                raise TechemAuthError("Invalid Techem username or password!")

            soup2 = BeautifulSoup(r2.text, "html.parser")
            form2 = soup2.find("form")
            if not form2:
                raise TechemParseError("Post-login page not found")

            action2 = form2.get("action")
            self._post_action = BASE_URL + action2 if action2.startswith("/") else action2
            return r2.text

        except requests.RequestException as err:
            raise TechemConnectionError(f"Communication error with Techem: {err}") from err

    def fetch_data(self) -> TechemData:
        """Fetch monthly totals and parse all meter consumption datasets."""
        if not self._post_action:
            self.login()

        assert self._post_action is not None

        try:
            # POST to select M43=2 (Totaux mensuels)
            mensuel_data = {
                "WD_JSON_PROPRIETE_": '{"m_oProprietesSecurisees":{}}',
                "WD_BUTTON_CLICK_": "M43",
                "WD_ACTION_": "",
                "M43": "2",
            }
            resp = self.session.post(self._post_action, data=mensuel_data, timeout=self.timeout)
            if resp.status_code != 200:
                raise TechemConnectionError(
                    f"Failed to fetch monthly totals: HTTP {resp.status_code}"
                )

            data = self._parse_monthly_page(resp.text)

            # Also fetch bimonthly (15-day) consumption if available
            try:
                bimonthly_results = self._fetch_bimonthly_data()
                for m_type, bimonthly_vals in bimonthly_results.items():
                    if m_type in data.meters:
                        data.meters[m_type].bimonthly_consumption = bimonthly_vals
            except Exception as err:
                _LOGGER.debug("Bimonthly data unavailable or ignored: %s", err)

            return data

        except requests.RequestException as err:
            raise TechemConnectionError(f"Error fetching Techem data: {err}") from err


    def _parse_monthly_page(self, html: str) -> TechemData:
        """Parse raw HTML and embedded XML tables from Techem monthly view."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract building / apartment info
        building_info = ""
        for tr in soup.find_all("tr"):
            txt = tr.get_text()
            if "Immeuble" in txt and "Appartement" in txt:
                raw_info = " ".join(tr.stripped_strings)
                # Clean up web portal artifacts like 'Déconnexion', user account ID, etc.
                if "Immeuble" in raw_info:
                    m = re.search(r"(Immeuble\s+\d+.*)", raw_info)
                    if m:
                        raw_info = m.group(1)
                building_info = re.sub(r"\s+", " ", raw_info).strip()
                break

        # Extract XML tables encoded inside WebDev JavaScript strings
        raw_blocks = re.findall(
            r"(?:\\\\x3C|\\x3C)COLONNES(?:\\\\x3E|\\x3E).*?(?:\\\\x3C|\\x3C)/LIGNES(?:\\\\x3E|\\x3E)",
            html,
            re.DOTALL,
        )

        # In Techem EnergyCoach WebDev 26:
        # Block 0: Annual history table
        # Block 1: Sub-metering / Heat cost allocators (if present)
        # Block 2: Hot Water
        # Block 3: Cold Water
        # Block 4: Heating
        block_types = ["repartiteur", "eau_chaude", "eau_froide", "chauffage"]

        data = TechemData(building_info=building_info)
        meter_block_idx = 0

        for idx, block in enumerate(raw_blocks):
            clean_block = (
                block.replace(r"\\x3C", "<")
                .replace(r"\x3C", "<")
                .replace(r"\\x3E", ">")
                .replace(r"\x3E", ">")
                .replace(r'\\\"', '"')
                .replace(r'\"', '"')
                .replace(r"\\xa0", " ")
                .replace(r"\xa0", " ")
            )
            wrapped = f"<TABLE>{clean_block}</TABLE>"
            try:
                root = ET.fromstring(wrapped)
            except Exception as err:
                _LOGGER.warning("Failed to parse XML block #%s: %s", idx, err)
                continue

            titles = [c.get("TITRE", "") for c in root.findall("./COLONNES/COLONNE")]
            rows = [[c.text for c in r.findall("./COLONNE")] for r in root.findall("./LIGNES/LIGNE")]

            if idx == 0:
                # Annual history
                for r in rows:
                    if len(r) >= 13 and r[2]:
                        data.annual_history.append({
                            "date": r[2].strip() if r[2] else "",
                            "type": r[4].strip() if r[4] else "",
                            "repartiteur": r[9].strip() if r[9] else "0",
                            "eau_chaude": r[10].strip().replace("\xa0", "").replace(" ", "") if r[10] else "0",
                            "eau_froide": r[11].strip().replace("\xa0", "").replace(" ", "") if r[11] else "0",
                            "chauffage": r[12].strip().replace("\xa0", "").replace(" ", "") if r[12] else "0",
                        })
            else:
                m_type = block_types[meter_block_idx] if meter_block_idx < len(block_types) else f"meter_{meter_block_idx}"
                meter_block_idx += 1

                for r in rows:
                    if len(r) >= 3 and r[0] and r[0].isdigit():
                        meter_id = r[0]
                        location = r[1] or "Indéfini"
                        months = titles[2:len(r)]
                        monthly_vals: dict[str, float] = {}

                        for m_title, val_str in zip(months, r[2:]):
                            if m_title and val_str is not None:
                                try:
                                    monthly_vals[m_title] = float(
                                        val_str.replace(",", ".").replace(" ", "")
                                    )
                                except ValueError:
                                    pass

                        latest_month = months[-1] if months else ""
                        latest_raw = monthly_vals.get(latest_month, 0.0)
                        exercise_total_raw = sum(monthly_vals.values())

                        # For water: convert hL (hectoliters) to m3 (1 hL = 0.1 m3)
                        # For heat: keep raw units
                        is_water = "eau" in m_type
                        latest_converted = latest_raw * 0.1 if is_water else latest_raw
                        total_converted = exercise_total_raw * 0.1 if is_water else exercise_total_raw

                        data.meters[m_type] = MeterReading(
                            meter_id=meter_id,
                            meter_type=m_type,
                            location=location,
                            current_month=latest_month,
                            current_value_raw=latest_raw,
                            current_value_m3_or_units=round(latest_converted, 3),
                            exercise_total_raw=exercise_total_raw,
                            exercise_total_m3_or_units=round(total_converted, 3),
                            monthly_consumption=monthly_vals,
                        )

        return data

    def _fetch_bimonthly_data(self) -> dict[str, dict[str, float]]:
        """Fetch and parse semi-monthly (15-day) consumption tables via M43=3."""
        if not self._post_action:
            return {}

        bimonthly_post = {
            "WD_JSON_PROPRIETE_": '{"m_oProprietesSecurisees":{}}',
            "WD_BUTTON_CLICK_": "M43",
            "WD_ACTION_": "",
            "M43": "3",
        }
        resp = self.session.post(self._post_action, data=bimonthly_post, timeout=self.timeout)
        if resp.status_code != 200:
            return {}

        return self._parse_bimonthly_html(resp.text)

    def _parse_bimonthly_html(self, html: str) -> dict[str, dict[str, float]]:
        """Parse 24-period bimonthly HTML tables from Techem."""
        soup = BeautifulSoup(html, "html.parser")
        tables: list[tuple[str, list[tuple[str, float]]]] = []

        for t in soup.find_all("table"):
            rows: list[tuple[str, float]] = []
            for tr in t.find_all("tr"):
                cells = [c.get_text().strip() for c in tr.find_all(["td", "th"])]
                if len(cells) == 2 and re.match(r"^\d{4}/\d{2}/\d{2}$", cells[0]):
                    clean_val = re.sub(r"[^\d.]", "", cells[1].replace(",", "."))
                    try:
                        rows.append((cells[0], float(clean_val)))
                    except ValueError:
                        pass
            if len(rows) >= 12:
                if not any(r == rows for _, r in tables):
                    prev = t.find_previous(
                        lambda el: el.name in ["td", "div", "span", "p"]
                        and any(
                            h in el.get_text()
                            for h in ["Eau chaude", "Eau froide", "Divers", "Chauffage", "partiteur"]
                        )
                    )
                    h_text = prev.get_text().strip() if prev else ""
                    tables.append((h_text, rows))

        meter_data: dict[str, dict[str, float]] = {}
        for h, rows in tables:
            m_type = None
            h_lower = h.lower()
            if "chaude" in h_lower:
                m_type = "eau_chaude"
            elif "froide" in h_lower:
                m_type = "eau_froide"
            elif "divers" in h_lower or "chauffage" in h_lower:
                m_type = "chauffage"
            elif "partiteur" in h_lower:
                m_type = "repartiteur"

            if m_type and m_type not in meter_data:
                meter_data[m_type] = dict(rows)

        return meter_data

