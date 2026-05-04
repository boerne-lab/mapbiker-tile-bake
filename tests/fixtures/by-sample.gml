<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
                xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
                xmlns:gml="http://www.opengis.net/gml">
  <!--
    One synthetic LoD2 building in Bayern (München central UTM32N coordinates).
    Pyramidal roof (code 3300), 14 m total height. Coordinates fall inside
    the BY tile (690, 5334) and inside the z14 web-mercator tile around
    lat=48.137, lon=11.575.
  -->
  <core:cityObjectMember>
    <bldg:Building gml:id="DEBY_TEST_001">
      <bldg:measuredHeight uom="urn:adv:uom:m">14.0</bldg:measuredHeight>
      <bldg:roofType>3300</bldg:roofType>
      <bldg:lod2Solid>
        <gml:Solid>
          <gml:exterior>
            <gml:CompositeSurface>
              <gml:surfaceMember>
                <gml:Polygon>
                  <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="3">
                        691400 5335870 520.0
                        691410 5335870 520.0
                        691410 5335880 520.0
                        691400 5335880 520.0
                        691400 5335870 520.0
                      </gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>
                </gml:Polygon>
              </gml:surfaceMember>
            </gml:CompositeSurface>
          </gml:exterior>
        </gml:Solid>
      </bldg:lod2Solid>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
