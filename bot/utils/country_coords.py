"""
Маппинг ISO 3166-1 alpha-2 (country_code) → [lat, lng] — приблизительные координаты центра/столицы страны.
Используется для автоматического размещения маркеров нод на карте по данным Remnawave.
"""
# ISO 3166-1 alpha-2 → (lat, lng)
COUNTRY_COORDS = {
    "AD": (42.5063, 1.5218),   # Andorra
    "AE": (23.4241, 53.8478),  # UAE
    "AF": (33.9391, 67.7100),  # Afghanistan
    "AL": (41.1533, 20.1683),  # Albania
    "AM": (40.0691, 45.0382),  # Armenia
    "AO": (-11.2027, 17.8739), # Angola
    "AR": (-38.4161, -63.6167),# Argentina
    "AT": (47.5162, 14.5501),  # Austria
    "AU": (-25.2744, 133.7751),# Australia
    "AZ": (40.1431, 47.5769),  # Azerbaijan
    "BA": (43.9159, 17.6791),  # Bosnia
    "BD": (23.6850, 90.3563),  # Bangladesh
    "BE": (50.5039, 4.4699),   # Belgium
    "BG": (42.7339, 25.4858),  # Bulgaria
    "BH": (26.0667, 50.5577),  # Bahrain
    "BN": (4.5353, 114.7277),  # Brunei
    "BO": (-16.2902, -63.5887),# Bolivia
    "BR": (-14.2350, -51.9253),# Brazil
    "BY": (53.7098, 27.9534),  # Belarus
    "CA": (56.1304, -106.3468),# Canada
    "CH": (46.8182, 8.2275),   # Switzerland
    "CL": (-35.6751, -71.5430),# Chile
    "CN": (35.8617, 104.1954), # China
    "CO": (4.5709, -74.2973),  # Colombia
    "CR": (9.7489, -83.7534),  # Costa Rica
    "CU": (21.5218, -77.7812), # Cuba
    "CY": (35.1264, 33.4299),  # Cyprus
    "CZ": (49.8175, 15.4730),  # Czech
    "DE": (51.1657, 10.4515),  # Germany
    "DK": (56.2639, 9.5018),   # Denmark
    "DO": (18.7357, -70.1627), # Dominican Republic
    "DZ": (28.0339, 1.6596),   # Algeria
    "EC": (-1.8312, -78.1834), # Ecuador
    "EE": (58.5953, 25.0136),  # Estonia
    "EG": (26.8206, 30.8025),  # Egypt
    "ES": (40.4637, -3.7492),  # Spain
    "FI": (61.9241, 25.7482),  # Finland
    "FR": (46.2276, 2.2137),   # France
    "GB": (55.3781, -3.4360),  # UK
    "GE": (42.3154, 43.3569),  # Georgia
    "GH": (7.9465, -1.0232),   # Ghana
    "GR": (39.0742, 21.8243),  # Greece
    "HK": (22.3193, 114.1694), # Hong Kong
    "HR": (45.1, 15.2),        # Croatia
    "HU": (47.1625, 19.5033),  # Hungary
    "ID": (-0.7893, 113.9213), # Indonesia
    "IE": (53.1424, -7.6921),  # Ireland
    "IL": (31.0461, 34.8516),  # Israel
    "IN": (20.5937, 78.9629),  # India
    "IR": (32.4279, 53.6880),  # Iran
    "IS": (64.9631, -19.0208), # Iceland
    "IT": (41.8719, 12.5674),  # Italy
    "JP": (36.2048, 138.2529), # Japan
    "KE": (-0.0236, 37.9062),  # Kenya
    "KG": (41.2044, 74.7661),  # Kyrgyzstan
    "KH": (12.5657, 104.9910), # Cambodia
    "KR": (35.9078, 127.7669), # South Korea
    "KZ": (48.0196, 66.9237),  # Kazakhstan
    "LA": (19.8563, 102.4955), # Laos
    "LB": (33.8547, 35.8623),  # Lebanon
    "LK": (7.8731, 80.7718),   # Sri Lanka
    "LT": (55.1694, 23.8813),  # Lithuania
    "LU": (49.8153, 6.1296),   # Luxembourg
    "LV": (56.8796, 24.6032),  # Latvia
    "LY": (26.3351, 17.2283),  # Libya
    "MA": (31.7917, -7.0926),  # Morocco
    "MD": (47.4116, 28.3699),  # Moldova
    "ME": (42.7087, 19.3744),  # Montenegro
    "MK": (41.6086, 21.7453),  # North Macedonia
    "MN": (46.8625, 103.8467), # Mongolia
    "MX": (23.6345, -102.5528),# Mexico
    "MY": (4.2105, 101.9758),  # Malaysia
    "NG": (9.0820, 8.6753),    # Nigeria
    "NL": (52.1326, 5.2913),   # Netherlands
    "NO": (60.4720, 8.4689),   # Norway
    "NZ": (-40.9006, 174.8860),# New Zealand
    "PA": (8.5380, -80.7821),  # Panama
    "PE": (-9.1900, -75.0152), # Peru
    "PH": (12.8797, 121.7740), # Philippines
    "PK": (30.3753, 69.3451),  # Pakistan
    "PL": (51.9194, 19.1451),  # Poland
    "PT": (39.3999, -8.2245),  # Portugal
    "QA": (25.2854, 51.5310),  # Qatar
    "RO": (45.9432, 24.9668),  # Romania
    "RS": (44.0165, 21.0059),  # Serbia
    "RU": (61.5240, 105.3188), # Russia
    "SA": (23.8859, 45.0792),  # Saudi Arabia
    "SE": (60.1282, 18.6435),  # Sweden
    "SG": (1.3521, 103.8198),  # Singapore
    "SI": (46.1512, 14.9955),  # Slovenia
    "SK": (48.6690, 19.6990),  # Slovakia
    "TH": (15.8700, 100.9925), # Thailand
    "TN": (33.8869, 9.5375),   # Tunisia
    "TR": (38.9637, 35.2433),  # Turkey
    "TW": (23.6978, 120.9605), # Taiwan
    "UA": (48.3794, 31.1656),  # Ukraine
    "US": (37.0902, -95.7129), # USA
    "UZ": (41.3775, 64.5853),  # Uzbekistan
    "VN": (14.0583, 108.2772), # Vietnam
    "ZA": (-30.5595, 22.9375), # South Africa
    "XX": (0, 0),              # Unknown/fallback
}


def get_coords_for_country(country_code: str | None) -> tuple[float, float]:
    """
    Возвращает (lat, lng) для country_code. Если код неизвестен — (0, 0).
    """
    if not country_code or not isinstance(country_code, str):
        return (0.0, 0.0)
    cc = country_code.upper().strip()
    return COUNTRY_COORDS.get(cc, (0.0, 0.0))
