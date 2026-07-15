import unittest


class ApplicationModuleTests(unittest.TestCase):
    def test_gui_module_imports(self):
        from countdownapp.app import CountdownApp

        self.assertEqual("CountdownApp", CountdownApp.__name__)



if __name__ == "__main__":
    unittest.main()
