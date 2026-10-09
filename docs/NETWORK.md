# Home network

Current as of 2026-10-09 (after replacing the Spectrum router with an ASUS RT-BE58U).

## Layout

```
Spectrum modem (192.168.100.1 admin)
  └─ ASUS RT-BE58U  192.168.50.1   (no double NAT; IPv6 off)
       ├─ Wi-Fi "5016Shoreside"        primary: PCs, phones, servers
       ├─ Wi-Fi "SpectrumSetup-DB35"   old name kept so IoT devices didn't need re-pairing
       └─ Ethernet: horae
```

Public IPv4 is a normal (non-CGNAT) Spectrum address and can change; nothing depends on it.

## Addresses

DHCP pool: `192.168.50.100`–`.254`. Reservations below `.100` are for machines that host things.

| IP | Device | MAC | Link |
|---|---|---|---|
| 192.168.50.1 | ASUS router | | |
| **192.168.50.2** | **horae** (Pi-hole DNS, Home Assistant, Homepage) | `88:A2:9E:6F:6F:45` | Ethernet |
| 192.168.50.3 | helios | `C0:B6:F9:A7:70:15` | Wi-Fi, 5016Shoreside |
| 192.168.50.4 | helios (Ethernet, if plugged in) | `98:28:A6:1A:6C:1E` | |
| 192.168.50.5 | hephaestus | `AC:F2:3C:77:F6:89` | Wi-Fi, 5016Shoreside (Wi-Fi 7, 160 MHz) |
| 192.168.50.6 | hephaestus (Ethernet) | `D8:5E:D3:E5:66:6E` | |

Laptops, phones and IoT devices get automatic addresses. Tailscale addresses (100.x) never change and are what
the apps use between machines.

## DNS

- ASUS: LAN > DHCP Server > DNS Server 1 = `192.168.50.2`, DNS Server 2 empty,
  "Advertise router's IP in addition to user-specified DNS" = **No**. So every device on both Wi-Fi networks
  uses Pi-hole, including IoT devices.
- Pi-hole asks the ASUS for device names (conditional forwarding: `dns.revServers =
  true,192.168.50.0/24,192.168.50.1,lan`), set in `horae/stack/docker-compose.yml`. Network Watch uses those names.
- `horae.home` -> `192.168.50.2` (Pi-hole local record, also in the compose file).
- Tailscale DNS: global nameserver `100.123.23.100` with Override on, so devices use Pi-hole while on Tailscale away
  from home too.
- IPv6 is off on the ASUS. If it's ever turned on, point its IPv6 DNS at the Pi, or devices can skip Pi-hole.
- Not used: ASUS AiProtection/AdGuard DNS, DNS Director. (DNS Director could force devices with hard-coded DNS through
  Pi-hole, but needs a "no redirect" exception for horae first, or Pi-hole's own upstream queries loop.)

## Port forwards

| Name | Protocol | Port | To |
|---|---|---|---|
| Dragonwilds | UDP | 7777 | 192.168.50.3:7777 (game) |
| Dragonwilds beacon | UDP | 8888 | 192.168.50.3:8888 (join handshake) |

helios' UFW allows the same two ports. After a public IP change, restart the server
(`sudo systemctl restart dragonwilds`) so the in-game server browser picks up the new address.

## Moving a headless server to another Wi-Fi network

```bash
scp scripts/wifi-switch.sh <host>:      # helios / hephaestus (netplan + systemd-networkd)
ssh <host>
sudo bash ~/wifi-switch.sh "5016Shoreside"
cat /var/log/wifi-switch.log             # OK or ROLLED BACK
```

It rewrites `/etc/netplan/60-wifi.yaml`, applies it as a separate systemd job and restores the backup by itself if the
new network isn't working within 2 minutes.
