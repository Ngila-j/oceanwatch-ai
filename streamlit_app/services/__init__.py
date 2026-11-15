"""OceanWatch Streamlit service layer."""

__all__ = [
    "VesselTrackingService",
    "PortIntelligenceService",
    "HomeCockpitService",
    "KPAShippingService",
    "LiveFeedsService",
    "PortOpsBoardService",
]


def __getattr__(name: str):
    if name == "VesselTrackingService":
        from services.vessel_tracking import VesselTrackingService

        return VesselTrackingService
    if name == "PortIntelligenceService":
        from services.port_intelligence import PortIntelligenceService

        return PortIntelligenceService
    if name == "HomeCockpitService":
        from services.home_cockpit import HomeCockpitService

        return HomeCockpitService
    if name == "KPAShippingService":
        from services.kpa_shipping import KPAShippingService

        return KPAShippingService
    if name == "LiveFeedsService":
        from services.live_feeds import LiveFeedsService

        return LiveFeedsService
    if name == "PortOpsBoardService":
        from services.port_ops_board import PortOpsBoardService

        return PortOpsBoardService
    raise AttributeError(name)
