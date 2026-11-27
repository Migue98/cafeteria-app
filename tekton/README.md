# Tekton

Estado: diseño preparado; todavía no hay Tasks, Pipelines ni Triggers implementados.
El [plan de CI/CD](../docs/tekton-ci-cd.md) describe las etapas, las credenciales,
la condición de aprobación E2E y el contrato con GitOps.

Recorrido previsto:

```text
push a main → webhook → clonar SHA → contratos y pruebas
             → exigir E2E del mismo SHA → construir y publicar 4 imágenes
             → actualizar GitOps → Argo CD sincroniza
```

Recursos por implementar:

- Task de clonación.
- Tasks de validación OpenAPI y pruebas por componente.
- Task que comprueba la aprobación E2E del mismo commit en GitHub Actions.
- Task de construcción y publicación con Buildah.
- Task de actualización del repositorio GitOps.
- Pipeline y ejemplo de PipelineRun manual de validación.
- TriggerBinding, TriggerTemplate y EventListener para GitHub.
- ServiceAccounts y permisos de ejecución.

Primero se validará la ejecución manual de clonación y pruebas; después se
añadirán publicación, GitOps y webhook. La versión de Tekton, la StorageClass
y el contexto de seguridad del builder se acordarán con el clúster real.

Las credenciales se crearán como Secrets del clúster y nunca se incluirán aquí.
Preparar estos archivos no instala componentes ni modifica el clúster.
