# Only used if D-DISPLAY picks the kit's screen. Driver chosen at bring-up B4
# once its controller and bus are known (esp_lcd: ST7789 / SSD1306 built in, ILI9341 / ST7735 from the
# component registry). Add the matching REQUIRES then.
idf_component_register(
    SRCS "display.c"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_lcd esp_driver_spi esp_driver_gpio
)
