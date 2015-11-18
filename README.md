# syncthing-relaysrv-status
Status server for the Syncthing Relay server network.

Blake VandeMerwe <blakev@null.net>

```bash
$: pip install -r requirements.txt
$: python -m viewserver.run
Serving on http://localhost:5000
```

## Usage
```bash
$: curl -L http://localhost:5000/status
{
  "162.216.226.77": {
    "host": "162.216.226.77",
    "meta": {
      "arch": {
        "go": null,
        "go_max_procs": 1,
        "go_version": "go1.4.3",
        "os": "linux"
      },
      "bytes_proxied": {
        "pretty": "180.3 GB",
...
...
```




