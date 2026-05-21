from appp import *

years = range(2015,2026)

for item in coastal_data:

    province = item['label']

    print("Running:", province)

    for year in years:

        try:

            region = provinces_fc.filter(

                ee.Filter.inList(
                    'ADM1_NAME',
                    item['search']
                )
            )

            aoi = region.geometry()

            offshore_zone = (
                aoi
                .buffer(500)
                .difference(aoi,1)
            )

            r = get_analysis(
                offshore_zone,
                year
            )

            erosion = 0
            accretion = 0

            save_data(

                province,
                year,

                r['vals']['NDWI'],
                r['vals']['MNDWI'],

                erosion,
                accretion
            )

            print(year,"done")

        except Exception as e:

            print(e)