{{- define "snell-server.validateValues" -}}
{{- $psk := .Values.snellServer.psk -}}
{{- if not (kindIs "string" $psk) -}}
{{- fail "snellServer.psk must be a string containing 12 to 255 bytes (required by Snell v6)" -}}
{{- end -}}
{{- if or (lt (len $psk) 12) (gt (len $psk) 255) -}}
{{- fail "snellServer.psk must contain 12 to 255 bytes (required by Snell v6)" -}}
{{- end -}}
{{- end -}}

{{- define "snell-server.image" -}}
{{ include "common.images.image" (dict "imageRoot" .Values.snellServer.image "global" .Values.global) }}
{{- end -}}

{{- define "snell-server.imagePullSecrets" -}}
{{- $images := list .Values.snellServer.image -}}
{{- if .Values.shadowTLS.enabled -}}
{{- $images = append $images .Values.shadowTLS.image -}}
{{- end -}}
{{ include "common.images.renderPullSecrets" (dict "images" $images "context" $) }}
{{- end -}}

{{- define "shadow-tls.image" -}}
{{ include "common.images.image" (dict "imageRoot" .Values.shadowTLS.image "global" .Values.global) }}
{{- end -}}

{{- define "snell-server.hostSNI" -}}
{{- if .Values.traefik.ingressRouteTCP.hostSNI -}}
{{- tpl .Values.traefik.ingressRouteTCP.hostSNI $ -}}
{{- else -}}
{{- tpl .Values.shadowTLS.sni $ -}}
{{- end -}}
{{- end -}}

{{- define "snell-server.ingressRouteTCPName" -}}
{{- if .Values.traefik.ingressRouteTCP.name -}}
{{- tpl .Values.traefik.ingressRouteTCP.name $ -}}
{{- else -}}
{{- printf "%s-%d" (include "common.names.fullname" .) (int .Values.shadowTLS.port) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
