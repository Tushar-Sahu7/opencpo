"""Plugin auto-discovery: imports plugins.{name}.routes and collects APIRouters."""
import importlib
import logging

logger = logging.getLogger(__name__)


def discover_plugins(names: list) -> list:
    """Import and return routers from enabled plugins."""
    routers = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        try:
            mod = importlib.import_module(f"plugins.{name}.routes")
            if hasattr(mod, "router"):
                routers.append(mod.router)
                logger.info(f"Plugin loaded: {name}")
            else:
                logger.warning(f"Plugin {name} has no router")
        except ImportError as e:
            logger.warning(f"Plugin {name} not found: {e}")
    return routers
