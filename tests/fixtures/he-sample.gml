<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
                xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
                xmlns:gml="http://www.opengis.net/gml">
  <!--
    One synthetic LoD2 building in Hessen (Frankfurt-area UTM32N coordinates).
    Gabled roof (code 3100), 12.5 m total height.
  -->
  <core:cityObjectMember>
    <bldg:Building gml:id="DEHE_TEST_001">
      <bldg:measuredHeight uom="urn:adv:uom:m">12.5</bldg:measuredHeight>
      <bldg:roofType>3100</bldg:roofType>
      <bldg:lod2Solid>
        <gml:Solid>
          <gml:exterior>
            <gml:CompositeSurface>
              <gml:surfaceMember>
                <gml:Polygon>
                  <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="3">
                        478253 5550160 100.0
                        478263 5550160 100.0
                        478263 5550170 100.0
                        478253 5550170 100.0
                        478253 5550160 100.0
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
