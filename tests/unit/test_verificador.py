from app.ai.verificador import verificar

FUENTES = "Flete base 65975. Seguro 125000. Total 190975. Guía TLX-984021-CO. Prohibido: animales vivos."


def test_cifras_respaldadas_pasan():
    assert verificar("El total es $190.975 e incluye seguro de $125.000.", FUENTES).ok


def test_cifra_inventada_falla():
    r = verificar("El total es $150.000.", FUENTES)
    assert not r.ok and r.motivo.startswith("cifras_sin_respaldo")


def test_guia_inventada_falla():
    assert verificar("Tu guía TLX-111111-CO va en camino.", FUENTES).motivo == "guia_inventada"


def test_polaridad_prohibido():
    assert not verificar("Sí, podemos enviar tu perro a Medellín.", FUENTES, "prohibido").ok
    assert verificar("No podemos transportar animales vivos: están prohibidos.", FUENTES, "prohibido").ok


def test_polaridad_permitido():
    assert not verificar("Ese producto está prohibido.", FUENTES, "restringido").ok


def test_decimales_y_parte_entera():
    assert verificar("Pesa 45,5 kg y el volumen da 30 kg.", "peso real 45.5 kg, volumétrico 30.00 kg").ok
    assert verificar("Pesa unos 45 kg.", "peso real 45.5 kg").ok
