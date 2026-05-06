import uuid
from gi.repository import Gio, GLib

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
BACKGROUND_INTERFACE = "org.freedesktop.portal.Background"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"


def request_background(autostart: bool, callback: callable) -> None:
    """
    Request background permission via xdg-desktop-portal.
    callback gets: (success: bool, background_granted: bool, autostart_granted: bool, error_msg: str)
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception as e:
        callback(False, False, False, str(e))
        return

    handle_token = f"hosty_{uuid.uuid4().hex}"
    
    sender_name = bus.get_unique_name()
    if not sender_name:
        sender_name = ""
    sender_name = sender_name.lstrip(":").replace(".", "_")
    
    expected_handle = f"/org/freedesktop/portal/desktop/request/{sender_name}/{handle_token}"

    subscription_id = None

    def on_response(connection, sender, object_path, interface_name, signal_name, parameters, user_data=None):
        nonlocal subscription_id
        if subscription_id is not None:
            connection.signal_unsubscribe(subscription_id)
            subscription_id = None
            
        try:
            response = parameters.get_child_value(0).get_uint32()
            results = parameters.get_child_value(1)
        except Exception:
            callback(False, False, False, "Invalid portal response.")
            return

        if response != 0:
            callback(False, False, False, "Background permission was not granted.")
            return

        def result_bool(key: str) -> bool:
            try:
                val = results.lookup_value(key, GLib.VariantType("b"))
                if val:
                    return val.get_boolean()
            except Exception:
                pass
            return False

        callback(
            True,
            result_bool("background"),
            result_bool("autostart"),
            ""
        )

    subscription_id = bus.signal_subscribe(
        PORTAL_BUS_NAME,
        REQUEST_INTERFACE,
        "Response",
        expected_handle,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response
    )

    options = {
        "handle_token": GLib.Variant("s", handle_token),
        "reason": GLib.Variant("s", "Hosty can keep Minecraft servers running in the background."),
        "autostart": GLib.Variant("b", autostart),
        "commandline": GLib.Variant("as", ["hosty", "--background"]),
    }
    
    try:
        bus.call(
            PORTAL_BUS_NAME,
            PORTAL_OBJECT_PATH,
            BACKGROUND_INTERFACE,
            "RequestBackground",
            GLib.Variant("(sa{sv})", ("", options)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
            None
        )
    except Exception as e:
        if subscription_id is not None:
            bus.signal_unsubscribe(subscription_id)
            subscription_id = None
        callback(False, False, False, f"Failed to request background: {e}")

def set_background_status(message: str) -> None:
    """Set the background status message."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call(
            PORTAL_BUS_NAME,
            PORTAL_OBJECT_PATH,
            BACKGROUND_INTERFACE,
            "SetStatus",
            GLib.Variant("(a{sv})", ({"message": GLib.Variant("s", message)},)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
            None
        )
    except Exception:
        pass