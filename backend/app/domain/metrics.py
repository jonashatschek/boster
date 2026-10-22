"""Catalogue of every financial metric the application knows about.

A metric definition is the single place that says what a metric means, which unit
it is stored in, and (for per-area metrics) which area it is divided by. Values with
different denominators get different metric keys so that they can never be compared
by accident, e.g. debt per m² of total area versus debt per m² of tenant-owned area.

Labels are in Swedish because they are shown directly in the UI.
"""

from dataclasses import dataclass
from enum import StrEnum


class Unit(StrEnum):
    SEK = "kr"
    SEK_PER_SQM = "kr/kvm"
    PERCENT = "%"
    SQM = "kvm"
    RATIO = "ggr"


class MetricCategory(StrEnum):
    BASE_FIGURE = "base_figure"  # Figures from the financial statements.
    AREA = "area"
    KEY_FIGURE = "key_figure"  # Ratios and per-area figures.


class AreaBasis(StrEnum):
    """The denominator of a per-m² metric."""

    TOTAL_AREA = "total_area"  # Residential + commercial (and sometimes garage) area.
    TENANT_OWNED_AREA = "tenant_owned_area"  # Area held with bostadsrätt only.


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    unit: Unit
    category: MetricCategory
    description: str
    area_basis: AreaBasis | None = None
    # True when the cooperative is required to print this figure in its annual report
    # (obligatoriska nyckeltal, mandatory for financial years starting 2023 or later).
    mandatory_since_2023: bool = False


_DEFINITIONS = [
    # Base figures from the income statement and balance sheet.
    MetricDefinition("net_revenue", "Nettoomsättning", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Föreningens intäkter från den normala verksamheten, främst årsavgifter och hyror."),
    MetricDefinition("operating_result", "Rörelseresultat", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Resultat före finansiella poster."),
    MetricDefinition("result_after_financial_items", "Resultat efter finansiella poster", Unit.SEK,
                     MetricCategory.BASE_FIGURE, "Resultat efter räntor men före skatt."),
    MetricDefinition("annual_result", "Årets resultat", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Årets vinst eller förlust enligt resultaträkningen."),
    MetricDefinition("depreciation", "Avskrivningar", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Årets avskrivningar. Påverkar resultatet men inte kassaflödet."),
    MetricDefinition("interest_expense", "Räntekostnader", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Räntekostnader och liknande resultatposter, angivet som positivt belopp."),
    MetricDefinition("total_assets", "Summa tillgångar", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Balansomslutning."),
    MetricDefinition("equity", "Eget kapital", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Summa eget kapital enligt balansräkningen."),
    MetricDefinition("interest_bearing_debt", "Räntebärande skulder", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Summa skulder till kreditinstitut, långfristiga och kortfristiga."),
    MetricDefinition("short_term_interest_bearing_debt", "Kortfristiga skulder till kreditinstitut",
                     Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Lån som förfaller eller ska omförhandlas inom ett år."),
    MetricDefinition("cash", "Kassa och bank", Unit.SEK, MetricCategory.BASE_FIGURE,
                     "Likvida medel på bankkonto och i kassa."),
    # Areas.
    MetricDefinition("residential_area", "Bostadsyta", Unit.SQM, MetricCategory.AREA,
                     "Total bostadsyta, inklusive eventuella hyreslägenheter."),
    MetricDefinition("commercial_area", "Lokalyta", Unit.SQM, MetricCategory.AREA,
                     "Yta för lokaler."),
    MetricDefinition("total_area", "Totalyta", Unit.SQM, MetricCategory.AREA,
                     "Bostadsyta plus lokalyta (ibland inklusive garage)."),
    MetricDefinition("tenant_owned_area", "Yta upplåten med bostadsrätt", Unit.SQM, MetricCategory.AREA,
                     "Den del av ytan som är upplåten med bostadsrätt."),
    # Key figures. Most are both printed in the report and calculable by us.
    MetricDefinition("debt_per_sqm_total_area", "Skuldsättning per kvm totalyta", Unit.SEK_PER_SQM,
                     MetricCategory.KEY_FIGURE, "Räntebärande skulder delat med totalyta.",
                     AreaBasis.TOTAL_AREA, mandatory_since_2023=True),
    MetricDefinition("debt_per_sqm_tenant_owned_area", "Skuldsättning per kvm bostadsrättsyta",
                     Unit.SEK_PER_SQM, MetricCategory.KEY_FIGURE,
                     "Räntebärande skulder delat med yta upplåten med bostadsrätt.",
                     AreaBasis.TENANT_OWNED_AREA, mandatory_since_2023=True),
    MetricDefinition("savings_per_sqm", "Sparande per kvm", Unit.SEK_PER_SQM, MetricCategory.KEY_FIGURE,
                     "(Årets resultat + avskrivningar + kostnadsfört planerat underhåll) / totalyta. "
                     "Visar hur mycket föreningen kan avsätta till framtida underhåll.",
                     AreaBasis.TOTAL_AREA, mandatory_since_2023=True),
    MetricDefinition("interest_sensitivity_pct", "Räntekänslighet", Unit.PERCENT, MetricCategory.KEY_FIGURE,
                     "Hur många procent årsavgifterna behöver höjas om räntan stiger en procentenhet. "
                     "Räntebärande skulder × 1 % / årsavgifter.", mandatory_since_2023=True),
    MetricDefinition("energy_cost_per_sqm", "Energikostnad per kvm", Unit.SEK_PER_SQM,
                     MetricCategory.KEY_FIGURE, "Kostnad för el, värme och vatten delat med totalyta.",
                     AreaBasis.TOTAL_AREA, mandatory_since_2023=True),
    MetricDefinition("annual_fee_per_sqm", "Årsavgift per kvm bostadsrättsyta", Unit.SEK_PER_SQM,
                     MetricCategory.KEY_FIGURE, "Årsavgifter delat med yta upplåten med bostadsrätt.",
                     AreaBasis.TENANT_OWNED_AREA, mandatory_since_2023=True),
    MetricDefinition("fee_share_of_revenue_pct", "Årsavgifternas andel av intäkterna", Unit.PERCENT,
                     MetricCategory.KEY_FIGURE,
                     "Andel av rörelseintäkterna som kommer från årsavgifter. "
                     "En låg andel betyder större beroende av hyror och andra intäkter.",
                     mandatory_since_2023=True),
    MetricDefinition("solidity_pct", "Soliditet", Unit.PERCENT, MetricCategory.KEY_FIGURE,
                     "Eget kapital delat med totala tillgångar. Säger relativt lite om en bostadsrättsförening, "
                     "eftersom det främst speglar hur fastigheten finansierades vid bildandet."),
    MetricDefinition("net_debt", "Nettoskuld", Unit.SEK, MetricCategory.KEY_FIGURE,
                     "Räntebärande skulder minus kassa och bank."),
    MetricDefinition("average_interest_rate_pct", "Genomsnittlig ränta (beräknad)", Unit.PERCENT,
                     MetricCategory.KEY_FIGURE,
                     "Räntekostnader delat med genomsnittet av räntebärande skulder vid årets början och slut. "
                     "En approximation, eftersom lån kan ha tagits upp eller amorterats under året."),
    MetricDefinition("interest_coverage_ratio", "Räntetäckningsgrad (kassaflödesbaserad)", Unit.RATIO,
                     MetricCategory.KEY_FIGURE,
                     "(Rörelseresultat + avskrivningar) / räntekostnader. Hur många gånger "
                     "det löpande överskottet täcker räntekostnaderna."),
    MetricDefinition("short_term_debt_share_pct", "Andel lån som förfaller inom ett år", Unit.PERCENT,
                     MetricCategory.KEY_FIGURE,
                     "Kortfristiga skulder till kreditinstitut delat med alla räntebärande skulder. "
                     "Ett högt värde betyder stor exponering för omförhandling inom ett år."),
]

METRICS: dict[str, MetricDefinition] = {definition.key: definition for definition in _DEFINITIONS}


def get_metric(key: str) -> MetricDefinition:
    try:
        return METRICS[key]
    except KeyError as error:
        raise ValueError(f"Unknown metric: {key}") from error
