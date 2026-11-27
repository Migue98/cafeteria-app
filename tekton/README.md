# Tekton

Estado: planeación actualizada el 27 de noviembre de 2026. Todavía no hay Tasks,
Pipeline ni Triggers implementados para la cafetería.

El [plan de trabajo](../docs/implementation-plan.md) incorpora las clases del
profesor; el [plan de CI/CD](../docs/tekton-ci-cd.md) precisa las tareas y resultados.

```text
push a main → webhook firmado → Tekton: clonar SHA, validar y probar
            → construir/publicar cuatro imágenes SHA y digests
            → actualizar cafeteria-gitops → Argo CD sincroniza
```

Las pruebas de integración y Chromium se ejecutarán desde Tekton. El diseño
anterior `wait-e2e`, dependiente de GitHub Actions, se sustituye por
`integration-tests` y un entorno aislado. Actions permanece como apoyo al desarrollo.

Preparar Tasks de clonación, contratos, pruebas Python, integración, build/push,
actualización GitOps y limpieza; Pipeline, PipelineRun manual, Triggers y RBAC.
La demo del profesor aporta workspace NFS, Task/Pipeline y `IMAGE_DIGEST`;
se adapta a cuatro Containerfiles y dos repositorios.

Siguiente paso: confirmar versiones, StorageClass y permisos con plataforma y
preparar el PipelineRun manual de clonación y validación. Los detalles de E2E y
builder se cierran antes de ampliar el pipeline. Secrets reales fuera de Git.
