from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import httpx
import os
import ssl

app = FastAPI()

SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
K8S_HOST = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
K8S_PORT = os.getenv("KUBERNETES_SERVICE_PORT", "443")
K8S_API = f"https://{K8S_HOST}:{K8S_PORT}"
NODE_IP = os.getenv("NODE_IP", "192.168.1.15")


def get_token():
    with open(SA_TOKEN_PATH) as f:
        return f.read().strip()


@app.get("/api/services")
async def get_services():
    token = get_token()
    ssl_context = ssl.create_default_context(cafile=SA_CA_PATH)
    
    async with httpx.AsyncClient(verify=SA_CA_PATH) as client:
        resp = await client.get(
            f"{K8S_API}/api/v1/services",
            headers={"Authorization": f"Bearer {token}"}
        )
        resp.raise_for_status()
        data = resp.json()

    services = []
    namespaces = set()

    for item in data.get("items", []):
        spec = item.get("spec", {})
        if spec.get("type") != "NodePort":
            continue

        name = item["metadata"]["name"]
        ns = item["metadata"]["namespace"]
        namespaces.add(ns)

        ports = []
        for p in spec.get("ports", []):
            node_port = p.get("nodePort")
            if node_port:
                ports.append({
                    "nodePort": node_port,
                    "port": p.get("port"),
                    "targetPort": str(p.get("targetPort", "")),
                    "protocol": p.get("protocol", "TCP"),
                    "name": p.get("name", ""),
                    "url": f"http://{NODE_IP}:{node_port}"
                })

        if ports:
            services.append({
                "name": name,
                "namespace": ns,
                "ports": ports
            })

    services.sort(key=lambda x: (x["namespace"], x["name"]))

    return JSONResponse({
        "nodeIp": NODE_IP,
        "services": services,
        "totalServices": len(services),
        "totalNamespaces": len(namespaces),
        "totalPorts": sum(len(s["ports"]) for s in services)
    })


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
