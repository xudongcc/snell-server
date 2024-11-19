{{- define "snell-server.image" -}}
{{ include "common.images.image" (dict "imageRoot" .Values.snellServer.image "global" .Values.global) }}
{{- end -}}

{{- define "snell-server.imagePullSecrets" -}}
{{ include "common.images.renderPullSecrets" (dict "images" (list .Values.snellServer.image .Values.shadowTLS.image) "context" $) }}
{{- end -}}

{{- define "shadow-tls.image" -}}
{{ include "common.images.image" (dict "imageRoot" .Values.shadowTLS.image "global" .Values.global) }}
{{- end -}}
