# Visor del registro de NVDA

prototipo de una interfaz para visualizar el registro de NVDA de forma estructurada en una vista de árbol, con posiblidad de aplicar filtros para encontrar la información más fácilmente.

## Funciones y atajos de teclado

* Al abrir el visor se carga automáticamente nvda.log desde %temp%.
* En el menú Archivo están las opciones para abrir nvda.log, nvda-old.log o cualquier archivo .log

El menú contextual del árbol tiene las opciones
- Exportar que guarda en un archivo de texto el contenido de la rama que cuelga del nodo seleccionado.
- Quitar filtro (control+Z) que limpia los filtros aplicados 

En la vista de detalle, cuando hay un Traceback, si se sitúa el cursor sobre una línea que haga referencia a un archivo .py y se pulsa la barra espaciadora se abrirá dicho archivo en la línea exacta a la que hace referencia el Traceback (sólo en vsCode, de momento no soporta otros editores).

### Atajos de teclado

* control+O Abre un archivo .log
* F5 recarga el archivo abierto.
* F6 cambia entre la vista en árborl por origen de los mensajes, la vista por niveles  y la vista cronológica.
* control+F lleva el foco al cuadro de edición de filtro.
* control+Z quita los filtros aplicados
* clic derecho o tecla aplicaciones en el árbol abre el menú contextual
* alt+F4 cierra la aplicación

