add_python_test(search PLUGIN gritsSearch)
if(PYTHON_STYLE_TESTS)
  add_python_style_test(pep8_style_grits
                        "${PROJECT_SOURCE_DIR}/plugins/gritsSearch/server")
endif()
