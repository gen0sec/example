# cert-manager on Kubernetes

A `SynapseProxy` of the Synapse operator serves an Ingress with a certificate
that cert-manager issues, and picks up the renewed certificate without a restart.
**Needs Synapse operator 0.2.0 (not released yet) and Synapse 0.8.8 or later.**

There is no `config.yaml` here. The operator renders Synapse's configuration
from the `SynapseProxy`, the Ingresses and their TLS Secrets, so the files are
Kubernetes manifests, applied in the order of their numbers:

| File | What it makes |
|---|---|
| `00-namespace.yaml` | two namespaces: `synapse-demo` for the proxy, with Pod Security `privileged`, and `synapse-demo-apps` for everything else |
| `10-cert-manager-issuers.yaml` | a self-signed `ClusterIssuer`, a CA certificate and a CA `ClusterIssuer`, `demo-ca` |
| `20-synapseproxy.yaml` | the `SynapseProxy` `edge` (HTTP on 80, TLS on 443) and the `IngressClass` that names it, both in `synapse-demo` |
| `30-whoami.yaml` | the back-end, in `synapse-demo-apps` |
| `40-ingress.yaml` | an Ingress for `app.example.com` in `synapse-demo-apps` that asks `demo-ca` for a certificate |
| `client.yaml` | a pod in `synapse-demo-apps` to curl the proxy from |
| `issuer-acme-http01.yaml` | an issuer for a real ACME server. **Not run, not part of the demo.** |

Things to know:

- **The operator is not released.** Version 0.2.0 is the branch `release/v0.2.0`
  of `gen0sec/synapse-operator`. The `SynapseProxy` API is alpha
  (`synapse.gen0sec.com/v1alpha1`) and the operator ignores it unless it runs with
  `--proxy-controller`. There is no published 0.2.0 image yet; the commands below
  build one.
- **Whoever may create a `SynapseProxy` gets a root pod.** The proxy pod is
  privileged and runs as root. Create, update and patch rights on `SynapseProxy`
  MUST go only to principals you trust with a root pod on those nodes. They also
  choose `hostNetwork`, `nodeSelector`, `tolerations` and `affinity`.
- **The namespace must allow a privileged pod.** Pod Security `baseline` or
  `restricted` refuses the pods and keeps the Deployment: the proxy never becomes
  Ready and `kubectl get synapseproxy` shows `RollingOut`. The label lifts Pod
  Security for every pod in the namespace, so the proxy gets a namespace of its
  own, and the back-end, the Ingress and the client live in `synapse-demo-apps`,
  which has no label. The Ingress may sit in another namespace than the proxy:
  the `IngressClass` (cluster-wide) names the `SynapseProxy`, and the operator
  reads the Ingress and its TLS Secret from where they are. Nothing else was
  needed in this run: no RBAC and no `hostOwnership` change.
- **Certificates reach the pod after about a minute.** The operator copies the
  TLS Secrets into the proxy's volume as `<host>.crt` and `<host>.key`, and the
  kubelet refreshes a mounted volume on its own schedule. Synapse watches the
  directory and loads a new certificate with no restart and no SIGHUP.
- **A host without a certificate gets the default one.** The operator makes a
  self-signed certificate, `_default` (CN `synapse-default`, no names, valid for a
  year), and the proxy serves it to a client that sends no SNI or a name no
  certificate matches. A client sees it as untrusted. The same happens to
  `app.example.com` between the start of the proxy and the issuance of its
  certificate, as the output below shows.
- **A host belongs to one namespace.** Within a proxy, the namespace whose Ingress
  claimed the host first gets it; an Ingress for the same host in another
  namespace loses that rule and its certificate, and gets a `HostnameConflict`
  warning. `spec.hostOwnership: None` turns this off.
- **Synapse's embedded ACME is not used.** cert-manager does the issuing. The
  proxy does not need to know the ACME server.
- **The certificate lives one hour here** (`cert-manager.io/duration` and
  `cert-manager.io/renew-before` on the Ingress) and is renewed five minutes
  after it is issued, so you can watch a rotation. Leave both annotations out
  for a real certificate. cert-manager takes one hour as the shortest duration.
- **The demo issues from a self-signed CA.** It has no public address, so no real
  ACME server could validate it. `issuer-acme-http01.yaml` is what a public
  cluster uses instead. **It was not run.** What the operator's README says about
  it, and nothing more: the solver's Ingress must name the proxy's class
  (`ingressClassName: edge`), and the operator then serves
  `/.well-known/acme-challenge/<token>` from the solver's Service.

## Run

What ran here: k3s v1.31.4 in a single-node container, cert-manager v1.21.3,
the operator built from `release/v0.2.0` at commit `93f76b1`, and Synapse
`ghcr.io/gen0sec/synapse:0.8.8`. Not run: a real ACME server, more than one
node, a load balancer, the Gateway API and a published operator image.

The cluster has no ingress from outside, so the requests come from a pod inside
it. Every command below needs `kubectl` pointed at a cluster you may break.

Install cert-manager. Its manifest includes the CRDs, and the issuers need its
webhook, so wait for it:

```sh
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.21.3/cert-manager.yaml
kubectl wait --for=condition=Available deploy --all -n cert-manager --timeout=300s
```

```text
deployment.apps/cert-manager condition met
deployment.apps/cert-manager-cainjector condition met
deployment.apps/cert-manager-webhook condition met
```

Build the operator from its release branch and install it with the CRD and
`--proxy-controller`. The cluster must be able to run the image: `docker save`
into k3s's `ctr` does that here, and a cluster with a registry pushes it there:

```sh
git clone --branch release/v0.2.0 https://github.com/gen0sec/synapse-operator
cd synapse-operator
docker build -t synapse-operator:local .
docker pull ghcr.io/gen0sec/synapse:0.8.8
docker save synapse-operator:local ghcr.io/gen0sec/synapse:0.8.8 \
  | docker exec -i <k3s container> ctr --namespace k8s.io images import -
kubectl apply -f <(kubectl kustomize test/e2e/operator)
kubectl -n synapse-os rollout status deploy/synapse-operator
cd ..
```

The Dockerfile asks for Go 1.26.10. If your Docker has an older `golang:1.26`
image, it stops at `go mod download`; pull the image again, or add
`ENV GOTOOLCHAIN=auto` after its `WORKDIR` line. (The run here did the latter and
tagged the image `synapse-operator:ex-cm2-93f76b1`.)

Apply the manifests in order, then the client:

```sh
cd use-cases/kubernetes-cert-manager
kubectl apply -f 00-namespace.yaml
kubectl apply -f 10-cert-manager-issuers.yaml -f 20-synapseproxy.yaml -f 30-whoami.yaml
kubectl apply -f client.yaml
kubectl -n synapse-demo-apps wait --for=condition=Ready pod/client --timeout=180s
```

The issuers and the proxy are ready, and the proxy has no certificate for
`app.example.com` yet:

```sh
kubectl get clusterissuer
kubectl get synapseproxy -n synapse-demo
```

```text
NAME              READY   AGE
demo-ca           True    45s
demo-selfsigned   True    45s
NAME   READY   REASON    DESIRED   AVAILABLE   ADDRESS        AGE
edge   True    Applied   1         1           10.43.103.10   43s
```

The bad case. `app.example.com` has no Ingress yet, so the proxy answers it with
its default certificate and a 404:

```sh
kubectl -n synapse-demo-apps exec client -- sh -c 'openssl s_client -connect edge.synapse-demo:443 -servername app.example.com </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -serial -enddate'
```

```text
subject=CN=synapse-default
issuer=CN=synapse-default
serial=30EF3EF4116B340B0D09810908A9DF19
notAfter=Nov  2 13:01:32 2027 GMT
```

Now the Ingress. cert-manager sees the annotation, makes a `Certificate`, and
issues it:

```sh
kubectl apply -f 40-ingress.yaml
kubectl -n synapse-demo-apps get certificate,secret,ingress
```

```text
NAME                                              READY   SECRET                AGE
certificate.cert-manager.io/app-example-com-tls   True    app-example-com-tls   16s

NAME                         TYPE                DATA   AGE
secret/app-example-com-tls   kubernetes.io/tls   3      16s

NAME                               CLASS   HOSTS             ADDRESS   PORTS     AGE
ingress.networking.k8s.io/whoami   edge    app.example.com             80, 443   16s
```

The `ADDRESS` of the Ingress stays empty; the proxy serves the host all the same.
The operator's own Secrets (`edge-certs`, `edge-config-...`) are in
`synapse-demo`, next to the proxy.

Within two minutes of the Ingress, the proxy serves the issued
certificate. The issuer is `demo-ca` and the name is in the SAN:

```sh
kubectl -n synapse-demo-apps exec client -- sh -c 'openssl s_client -connect edge.synapse-demo:443 -servername app.example.com </dev/null 2>/dev/null | openssl x509 -noout -issuer -serial -enddate -ext subjectAltName'
```

```text
issuer=CN=demo-ca
serial=66393209412FB2CCB0CB416E6A481BD1B551CB9C
notAfter=Nov  2 14:02:32 2026 GMT
X509v3 Subject Alternative Name: critical
    DNS:app.example.com
```

A request that verifies the certificate against the demo CA:

```sh
kubectl -n cert-manager get secret demo-ca -o jsonpath='{.data.ca\.crt}' | base64 -d \
  | kubectl -n synapse-demo-apps exec -i client -- sh -c 'cat > /tmp/ca.crt'
kubectl -n synapse-demo-apps exec client -- sh -c 'curl -sS --cacert /tmp/ca.crt --resolve app.example.com:443:$(getent hosts edge.synapse-demo | cut -d" " -f1) https://app.example.com/ | head -4; curl -sS --cacert /tmp/ca.crt --resolve app.example.com:443:$(getent hosts edge.synapse-demo | cut -d" " -f1) -o /dev/null -w "verify=%{ssl_verify_result} http=%{http_code}\n" https://app.example.com/'
```

```text
Hostname: whoami-cb676888c-84tr7
IP: 127.0.0.1
IP: ::1
IP: 10.42.0.11
verify=0 http=200
```

### Rotation

The Certificate was issued at 13:02:32 and renews at 13:07:32 (five minutes, by
the annotation). At 13:09:42 the Secret held a new serial and so did the proxy,
and the proxy pod was the one it had been since 13:01:33 (the log says the
volume was swapped at 13:07:41):

```text
2026-11-02T13:07:32Z renew=2026-11-02T13:12:32Z rev=2
serial=0B29FECC928BD2FE0C79D625B2ACD7196B7394EF       (the Secret)
serial=0B29FECC928BD2FE0C79D625B2ACD7196B7394EF       (served by the proxy)
```

To force a renewal, delete the Secret. cert-manager notices, issues again and
writes a new one. The proxy serves the new serial within a few minutes, and the
pod name, start time and restart count are the same before and after:

```sh
kubectl -n synapse-demo-apps delete secret app-example-com-tls
```

```text
== before (13:10:51)
serial=0B29FECC928BD2FE0C79D625B2ACD7196B7394EF
NAME                    RESTARTS   START
edge-7ff69b476b-blwpj   0          2026-11-02T13:01:33Z
secret "app-example-com-tls" deleted
== after (13:12:59)
2026-11-02T13:10:53Z rev=3
serial=3AEF0B220136CE73D23CECA12825B0F3ED7CECA8       (the Secret)
serial=3AEF0B220136CE73D23CECA12825B0F3ED7CECA8       (served by the proxy)
NAME                    RESTARTS   START
edge-7ff69b476b-blwpj   0          2026-11-02T13:01:33Z
```

The proxy logged each change (the first is the issuance), and no restart:

```text
Certificate changed: Create(Folder), ["/etc/synapse/certs/..2026_11_02_13_02_55.2983661074"]
Certificate changed: Create(Folder), ["/etc/synapse/certs/..2026_11_02_13_07_41.3957573335"]
Certificate changed: Create(Folder), ["/etc/synapse/certs/..2026_11_02_13_11_09.2443682852"]
```

Your serials, names and times differ.

### Clean up

```sh
kubectl delete -f client.yaml -f 40-ingress.yaml -f 30-whoami.yaml -f 20-synapseproxy.yaml
kubectl delete -f 10-cert-manager-issuers.yaml -f 00-namespace.yaml
kubectl -n cert-manager delete secret demo-ca
```

The last line is needed. The CA's private key stays in the Secret `demo-ca`
when its Certificate is deleted: cert-manager removes it only when it runs with
`--enable-certificate-owner-ref`, which is off by default. After the first two
commands `kubectl -n cert-manager get secret demo-ca` still showed it; after the
third it answers `NotFound`.

### Checking the manifests

`kubectl apply --dry-run=server -f <file>` accepted every file here against the
cluster above. `make lint` checks that the YAML is well formed. Nothing checks
the rendered Synapse configuration offline, because the operator makes it.
