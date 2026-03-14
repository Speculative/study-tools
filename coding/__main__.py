from . import create_app


def main() -> None:
    app = create_app()
    app.run(debug=True)


main()
