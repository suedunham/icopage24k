from make_ip24k_grids import run_grid_maker


def run_main() -> None:
    """Main run function."""
    # run_grid_maker(['ip24k_style.yml', 'ip24k_run.yml'])
    run_grid_maker('ip24k_style.yml')


run_main()
