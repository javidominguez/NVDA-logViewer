# Visor de registros mejorado

Complemento de NVDA que muestra el registro activo en una vista de árbol estructurada y permite filtrar entradas, inspeccionar tracebacks y gestionar marcadores.

El complemento sustituye al visor de registros estándar de NVDA cuando se abre. Carga el registro activo y actualiza la vista cuando NVDA escribe un mensaje que solicita mostrar el visor.

## Funciones

* El registro actual de NVDA se carga automáticamente al abrir el visor.
* Desde el menú Archivo se puede abrir `nvda.log`, `nvda-old.log` o cualquier archivo `.log`.
* Guardar como exporta las entradas de la vista actual, incluidos los filtros aplicados.
* El menú contextual del árbol permite exportar la rama seleccionada, borrar los filtros, añadir o quitar marcadores y ocultar entradas.
* En la vista de detalles, sitúa el cursor en una línea de un traceback y pulsa Espacio para abrir el archivo fuente referenciado en el editor configurado.
* Si se configura la carpeta del código fuente de NVDA, se puede resolver una referencia `.pyc` del traceback al archivo `.py` correspondiente.
* VS Code abre los archivos en la línea referenciada. A otros editores se les pasa la ruta del archivo y puede que no permitan navegar a una línea concreta.
* Los ajustes ofrecen VS Code si se detecta y el Bloc de notas de Windows. Usa Examinar para elegir otro ejecutable.

## Atajos de teclado

* F1: Abrir esta documentación.
* Ctrl+O: Abrir un archivo de registro.
* F5: Recargar el archivo actual.
* F6: Cambiar entre las vistas por origen, nivel y orden cronológico.
* Ctrl+F: Situar el foco en el cuadro de filtro.
* Ctrl+T: Situar el foco en el árbol de entradas.
* Con el foco en el árbol, Ctrl+1 a Ctrl+6: Activar o desactivar cada nivel de mensaje.
* Ctrl+Z: Borrar los filtros aplicados.
* Clic derecho o tecla Aplicaciones en el árbol: Abrir el menú contextual.
* Alt+F4 o Ctrl+Q: Cerrar el visor.
* Ctrl+M: Añadir o quitar el elemento actual de los marcadores.
